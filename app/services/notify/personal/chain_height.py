from collections import defaultdict
from typing import List

from services.lib.constants import Chains
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.depcont import DepContainer
from services.lib.utils import most_common
from services.models.thormon import ThorMonNodeTimeSeries, ThorMonAnswer
from services.notify.personal.telemetry import NodeTelemetryDatabase
from services.notify.personal.helpers import BaseChangeTracker
from services.models.node_info import NodeChange

TRIGGER_SWITCH_CD = 30.0  # sec


class ChainHeightTracker(BaseChangeTracker):
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.block_times = dict(deps.cfg.get_pure('blockchain.block_time', {}))
        for chain, en_time in self.block_times.items():
            self.block_times[chain] = parse_timespan_to_seconds(en_time)

        self.recent_max_blocks = {}

    def get_block_time(self, chain):
        return self.block_times.get(chain, Chains.block_time_default(chain))

    def blocks_to_lag(self, chain: str, seconds: float):
        return seconds / self.get_block_time(chain)

    def estimate_block_height(self, data: ThorMonAnswer):
        chain_block_height = defaultdict(list)
        for node in data.nodes:
            for chain_info in node.observe_chains:
                if chain_info.valid:
                    chain_block_height[chain_info.chain].append(chain_info.height)

        self.recent_max_blocks = {chain: most_common(height_list) for chain, height_list in chain_block_height.items()}

    async def get_node_changes(self, node_address, telemetry: ThorMonNodeTimeSeries):
        if not node_address:
            return []

        changes = []

        return changes

    async def filter_changes(self, ch_list: List[NodeChange], settings: dict) -> List[NodeChange]:
        return await super().filter_changes(ch_list, settings)
