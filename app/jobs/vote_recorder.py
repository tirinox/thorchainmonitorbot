import json
from collections import defaultdict
from typing import List, Dict

from api.aionode.types import ThorMimirVote
from jobs.runeyield.date2block import DateToBlockMapper
from lib.accumulator import Accumulator
from lib.date_utils import HOUR, format_time_ago, now_ts, YEAR
from lib.delegates import WithDelegates, INotified
from lib.depcont import DepContainer
from lib.logs import WithLogger
from models.mimir import MimirTuple, MimirVoting, MimirVoteOption


class VoteRecorder(WithLogger, WithDelegates, INotified):
    """
    Records:
        - mimir votes: who/what/when
        - voting progress daily snapshots, to be able to show progress charts
    """

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.accumulator = Accumulator("MimirVotes", deps.db, HOUR * 4)
        self.block_mapper = DateToBlockMapper(deps)

    @staticmethod
    def group_votes_by_option(votes: List[ThorMimirVote]) -> Dict[str, int]:
        vote_dict = defaultdict(int)
        for vote in votes:
            vote_dict[vote.value] += 1
        return vote_dict

    async def on_data(self, sender, data: MimirTuple):
        if not data.ts:
            self.logger.warning(f"No timestamp in MimirTuple, trying to get it from block height {data.thor_height}")
            date = await self.block_mapper.get_datetime_by_block_height(data.thor_height)
            data.ts = date.timestamp() if date else None
            if not data.ts:
                self.logger.error(f"Failed to get timestamp for block {data.thor_height}, using current time")
                return

        self.logger.info(
            f"Recording votes for mimir {format_time_ago(now_ts() - data.ts, max_time=YEAR)}: {len(data.votes)} votes")

        votes_grouped = data.votes_grouped_by_key
        packed = {}
        for key, votes in votes_grouped.items():
            vote_dict_count = self.group_votes_by_option(votes)
            packed[key] = json.dumps(vote_dict_count)

        await self.accumulator.set(data.ts, **packed)

    async def get_point(self, ts):
        return await self.accumulator.get(ts, conv_to_float=False)

    @staticmethod
    def snapshot_to_voting_list(snapshot: Dict[str, str], active_nodes: int,
                                key_filter: str = None) -> List[MimirVoting]:
        result = []
        for key, raw in snapshot.items():
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

    async def get_key_progress(self, key: str, duration_sec: float, active_nodes: int) \
            -> Dict[float, MimirVoting]:
        all_progress = await self.get_recent_progress(duration_sec, active_nodes, key_filter=key)
        return {
            ts: votings[0] if votings else None
            for ts, votings in all_progress.items()
            if votings
        }

    async def get_recent_progress(self, duration_sec: float, active_nodes: int,
                                  key_filter: str = None) -> Dict[float, List[MimirVoting]]:
        if duration_sec < self.accumulator.tolerance:
            raise ValueError(f"Duration must be at least {self.accumulator.tolerance} seconds")

        end_ts = now_ts()
        start_ts = end_ts - duration_sec
        points = await self.accumulator.get_range(start_ts, end_ts, conv_to_float=False)
        return {
            ts: self.snapshot_to_voting_list(snapshot, active_nodes, key_filter)
            for ts, snapshot in points.items()
        }
