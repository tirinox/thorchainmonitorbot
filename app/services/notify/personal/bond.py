from typing import List

from services.lib.depcont import DepContainer
from services.models.node_info import NodeEvent, MapAddressToPrevAndCurrNode, NodeEventType
from services.notify.personal.helpers import BaseChangeTracker


class BondTracker(BaseChangeTracker):
    def __init__(self, deps: DepContainer):
        self.deps = deps

    async def get_all_changes(self, pc_node_map: MapAddressToPrevAndCurrNode) -> List[NodeEvent]:
        return list(self._changes_of_bond(pc_node_map))

    @staticmethod
    def _changes_of_bond(pc_node_map: MapAddressToPrevAndCurrNode):
        for a, (prev, curr) in pc_node_map.items():
            if prev.bond != curr.bond:
                yield NodeEvent(prev.node_address, NodeEventType.BOND, (prev.bond, curr.bond),
                                node=curr)

    async def filter_events(self, ch_list: List[NodeEvent], settings: dict) -> List[NodeEvent]:
        return await super().filter_events(ch_list, settings)
