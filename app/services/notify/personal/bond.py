from typing import List

from services.lib.depcont import DepContainer
from services.models.node_info import NodeChange, MapAddressToPrevAndCurrNode, NodeChangeType
from services.notify.personal.helpers import BaseChangeTracker


class BondTracker(BaseChangeTracker):
    def __init__(self, deps: DepContainer):
        self.deps = deps

    async def get_all_changes(self, pc_node_map: MapAddressToPrevAndCurrNode) -> List[NodeChange]:
        return list(self._changes_of_bond(pc_node_map))

    @staticmethod
    def _changes_of_bond(pc_node_map: MapAddressToPrevAndCurrNode):
        for a, (prev, curr) in pc_node_map.items():
            if prev.bond != curr.bond:
                yield NodeChange(prev.node_address, NodeChangeType.BOND, (prev.bond, curr.bond))

    async def filter_changes(self, ch_list: List[NodeChange], settings: dict) -> List[NodeChange]:
        return await super().filter_changes(ch_list, settings)
