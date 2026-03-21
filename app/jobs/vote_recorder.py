import json
from collections import defaultdict
from typing import List, Dict, Iterable, Set, Optional

from jobs.runeyield.date2block import DateToBlockMapper
from lib.accumulator import Accumulator
from lib.date_utils import HOUR, format_time_ago, now_ts, YEAR
from lib.delegates import WithDelegates, INotified
from lib.depcont import DepContainer
from lib.logs import WithLogger
from models.mimir import MimirVoting, MimirVoteOption, MimirHolder, AlertMimirVoting


class VoteRecorder(WithLogger, WithDelegates, INotified):
    """
    Records:
        - mimir votes: who/what/when
        - voting progress daily snapshots, to be able to show progress charts
    """

    META_KEY_BLOCK_HEIGHT = '__block_height__'
    META_KEY_ACTIVE_NODES = '__active_nodes__'

    REDIS_KEY_VOTE_TIMESTAMPS = 'Mimir:Vote:Timestamps'  # hash: voting_key -> json {"first": ts, "last": ts, "signers": []}

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.accumulator = Accumulator("MimirVotes", deps.db, HOUR * 4)
        self.block_mapper = DateToBlockMapper(deps)

    async def clear_all(self) -> int:
        """Delete all recorded vote data: time-series accumulator entries and first/last-seen timestamps.
        Returns the total number of Redis keys removed."""
        n_accum = await self.accumulator.clear()
        await self.deps.db.redis.delete(self.REDIS_KEY_VOTE_TIMESTAMPS)
        self.logger.warning(f"Cleared all vote data: {n_accum} accumulator keys + timestamps hash deleted")
        return n_accum + 1

    # ------------------------------------------------------------------
    # Timestamp persistence helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_signers(signers: Iterable[str]) -> Set[str]:
        return {signer for signer in signers if signer}

    def _merge_vote_timestamp_data(self, raw: str, signers: Iterable[str], ts: float) -> dict:
        current_signers = self._normalize_signers(signers)

        if not raw:
            return {
                'first': ts,
                'last': ts,
                'signers': sorted(current_signers),
            }

        data = json.loads(raw)
        first_seen = min(float(data.get('first', ts)), ts)
        last_seen = float(data.get('last', first_seen))

        if 'signers' not in data:
            # Backward compatibility: existing records had only timestamps.
            # Seed the signer baseline without treating all current signers as newly added.
            return {
                'first': first_seen,
                'last': last_seen,
                'signers': sorted(current_signers),
            }

        stored_signers = self._normalize_signers(data.get('signers', []))
        if current_signers - stored_signers:
            last_seen = max(last_seen, ts)

        return {
            'first': first_seen,
            'last': last_seen,
            'signers': sorted(stored_signers | current_signers),
        }

    async def _update_vote_timestamps(self, signers_by_key: Dict[str, Iterable[str]], ts: float):
        """For each key: keep the earliest first_seen; update last_seen only when a new signer appears."""
        redis = self.deps.db.redis
        for key, signers in signers_by_key.items():
            raw = await redis.hget(self.REDIS_KEY_VOTE_TIMESTAMPS, key)
            data = self._merge_vote_timestamp_data(raw, signers, ts)
            await redis.hset(self.REDIS_KEY_VOTE_TIMESTAMPS, key, json.dumps(data))

    async def get_vote_timestamps(self, key: str) -> tuple:
        """Return (first_seen_ts, last_seen_ts) for the given voting key, or (0, 0) if unknown."""
        raw = await self.deps.db.redis.hget(self.REDIS_KEY_VOTE_TIMESTAMPS, key)
        if raw:
            data = json.loads(raw)
            return float(data.get('first', 0)), float(data.get('last', 0))
        return 0.0, 0.0

    async def get_all_vote_timestamps(self) -> Dict[str, tuple]:
        """Return {key: (first_seen_ts, last_seen_ts)} for all tracked voting keys."""
        all_raw = await self.deps.db.redis.hgetall(self.REDIS_KEY_VOTE_TIMESTAMPS)
        result = {}
        for k, v in all_raw.items():
            data = json.loads(v)
            result[k] = (float(data.get('first', 0)), float(data.get('last', 0)))
        return result

    async def enrich_with_timestamps(self, votings: List[MimirVoting]) -> List[MimirVoting]:
        """Populate first_seen_ts / last_seen_ts on a list of MimirVoting objects in-place."""
        all_ts = await self.get_all_vote_timestamps()
        for voting in votings:
            first, last = all_ts.get(voting.key, (0.0, 0.0))
            voting.first_seen_ts = first
            voting.last_seen_ts = last
        return votings

    async def sorted_by_recent_activity(self, votings: List[MimirVoting]) -> List[MimirVoting]:
        """Return votings sorted by most recent vote activity (latest last_seen_ts first).
        Also enriches each voting with persisted first/last-seen timestamps in one Redis round-trip."""
        await self.enrich_with_timestamps(votings)
        return sorted(votings, key=lambda v: v.last_seen_ts, reverse=True)

    # ------------------------------------------------------------------

    async def on_data(self, sender, data: MimirHolder):
        if not data.last_timestamp:
            self.logger.error(f"MimirHolder @ block = {data.last_timestamp} has no timestamp, skipping")
            return

        self.logger.info(
            f"Recording votes for mimir {format_time_ago(now_ts() - data.last_timestamp, max_time=YEAR)}: "
            f"{data.voting_manager.active_vote_count} votes, {data.voting_manager.active_node_count} nodes active")

        signers_by_key = defaultdict(set)
        for vote in data.voting_manager.votes:
            if vote.singer:
                signers_by_key[vote.key].add(vote.singer)

        packed = {}
        for voting in data.voting_manager.all_voting_list:
            packed[voting.key] = json.dumps(voting.short_dict)

        packed[self.META_KEY_BLOCK_HEIGHT] = data.last_thor_block
        packed[self.META_KEY_ACTIVE_NODES] = data.voting_manager.active_node_count

        await self.accumulator.set(data.last_timestamp, **packed)

        # Track first seen timestamps for every active voting key, and bump last seen only when a new signer appears.
        if signers_by_key:
            await self._update_vote_timestamps(signers_by_key, data.last_timestamp)

    async def get_point(self, ts):
        return await self.accumulator.get(ts, conv_to_float=False)

    @staticmethod
    def snapshot_to_voting_list(snapshot: Dict[str, str], key_filter: str = None) -> List[MimirVoting]:
        result = []

        active_nodes = int(snapshot.get(VoteRecorder.META_KEY_ACTIVE_NODES, 1))

        for key, raw in snapshot.items():
            if key == VoteRecorder.META_KEY_BLOCK_HEIGHT:
                continue
            if key_filter and key != key_filter:
                continue
            if not raw:
                continue
            try:
                counts: Dict[str, int] = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
            options = {
                int(value): MimirVoteOption(value=int(value), signer_count=count)
                for value, count in counts.items()
            }
            voting = MimirVoting(key=key, options=options, active_nodes_count=active_nodes)
            for opt in voting.options.values():
                opt.calculate_progress(voting.active_nodes_count)
            result.append(voting)

        return result

    async def get_key_progress(self, key: str, duration_sec: float) \
            -> Dict[float, MimirVoting]:
        all_progress = await self.get_recent_progress(duration_sec, key_filter=key)
        result = {
            ts: voting_list[0] if voting_list else None
            for ts, voting_list in all_progress.items()
            if voting_list
        }
        # Enrich with persisted timestamps
        first_seen, last_seen = await self.get_vote_timestamps(key)
        for voting in result.values():
            if voting is not None:
                voting.first_seen_ts = first_seen
                voting.last_seen_ts = last_seen
        return result

    async def get_alert_for_key(self, key: str, duration_sec: float,
                                holder: Optional[MimirHolder] = None,
                                triggered_option: Optional[MimirVoteOption] = None) -> Optional[AlertMimirVoting]:
        holder = holder or self.deps.mimir_const_holder
        if holder is None:
            return None

        voting_history = await self.get_key_progress(key, duration_sec)
        voting = holder.voting_manager.find_voting(key)

        if voting is None and voting_history:
            voting = voting_history[max(voting_history)]

        if voting is None:
            return None

        first_seen, last_seen = await self.get_vote_timestamps(key)
        voting.first_seen_ts = first_seen
        voting.last_seen_ts = last_seen

        return AlertMimirVoting(
            holder=holder,
            voting=voting,
            triggered_option=triggered_option,
            voting_history=voting_history,
        )

    async def get_recent_progress(self, duration_sec: float, key_filter: str = None) -> Dict[float, List[MimirVoting]]:
        if duration_sec < self.accumulator.tolerance:
            raise ValueError(f"Duration must be at least {self.accumulator.tolerance} seconds")

        end_ts = now_ts()
        start_ts = end_ts - duration_sec
        points = await self.accumulator.get_range(start_ts, end_ts, conv_to_float=False)
        result = {
            ts: self.snapshot_to_voting_list(snapshot, key_filter)
            for ts, snapshot in points.items()
        }
        # Enrich all unique voting keys with persisted timestamps
        all_ts = await self.get_all_vote_timestamps()
        for voting_list in result.values():
            for voting in voting_list:
                first, last = all_ts.get(voting.key, (0.0, 0.0))
                voting.first_seen_ts = first
                voting.last_seen_ts = last
        return result
