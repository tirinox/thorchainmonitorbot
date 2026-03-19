import json
from collections import defaultdict
from typing import List, Dict

from jobs.runeyield.date2block import DateToBlockMapper
from lib.accumulator import Accumulator
from lib.date_utils import HOUR, format_time_ago, now_ts, YEAR
from lib.delegates import WithDelegates, INotified
from lib.depcont import DepContainer
from lib.logs import WithLogger
from models.mimir import MimirVoting, MimirVoteOption, MimirHolder


class VoteRecorder(WithLogger, WithDelegates, INotified):
    """
    Records:
        - mimir votes: who/what/when
        - voting progress daily snapshots, to be able to show progress charts
    """

    BLOCK_SPECIAL_KEY = '__block_height__'

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.accumulator = Accumulator("MimirVotes", deps.db, HOUR * 4)
        self.block_mapper = DateToBlockMapper(deps)

    async def on_data(self, sender, data: MimirHolder):
        if not data.last_timestamp:
            self.logger.error(f"MimirHolder @ block = {data.last_timestamp} has no timestamp, skipping")
            return

        self.logger.info(
            f"Recording votes for mimir {format_time_ago(now_ts() - data.ts, max_time=YEAR)}: "
            f"{data.voting_manager.active_vote_count} votes")

        votes_grouped = defaultdict(list)
        for vote in data.voting_manager.votes:
            votes_grouped[vote.key].append(vote)

        packed = {}
        for voting in data.voting_manager.all_voting_list:
            packed[voting.key] = json.dumps(voting.short_dict)

        packed[self.BLOCK_SPECIAL_KEY] = data.last_thor_block

        await self.accumulator.set(data.ts, **packed)

    async def get_point(self, ts):
        return await self.accumulator.get(ts, conv_to_float=False)

    @staticmethod
    def snapshot_to_voting_list(snapshot: Dict[str, str], key_filter: str = None) -> List[MimirVoting]:
        result = []

        active_nodes = int(snapshot.get(VoteRecorder.BLOCK_SPECIAL_KEY, 1))

        for key, raw in snapshot.items():
            if key == VoteRecorder.BLOCK_SPECIAL_KEY:
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
            voting = MimirVoting(key=key, options=options, active_nodes=active_nodes)
            for opt in voting.options.values():
                opt.calculate_progress(voting.active_nodes)
            result.append(voting)

        return result

    async def get_key_progress(self, key: str, duration_sec: float) \
            -> Dict[float, MimirVoting]:
        all_progress = await self.get_recent_progress(duration_sec, key_filter=key)
        return {
            ts: voting_list[0] if voting_list else None
            for ts, voting_list in all_progress.items()
            if voting_list
        }

    async def get_recent_progress(self, duration_sec: float, key_filter: str = None) -> Dict[float, List[MimirVoting]]:
        if duration_sec < self.accumulator.tolerance:
            raise ValueError(f"Duration must be at least {self.accumulator.tolerance} seconds")

        end_ts = now_ts()
        start_ts = end_ts - duration_sec
        points = await self.accumulator.get_range(start_ts, end_ts, conv_to_float=False)
        return {
            ts: self.snapshot_to_voting_list(snapshot, key_filter)
            for ts, snapshot in points.items()
        }
