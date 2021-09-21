from typing import List

from services.lib.depcont import DepContainer
from services.models.node_info import MapAddressToPrevAndCurrNode, NodeChangeType, NodeChange
from services.notify.personal.helpers import BaseChangeTracker


class IpAddressTracker(BaseChangeTracker):
    def __init__(self, deps: DepContainer):
        self.deps = deps

    async def get_all_changes(self, pc_node_map: MapAddressToPrevAndCurrNode) -> List[NodeChange]:
        changes = []
        for a, (prev, curr) in pc_node_map.items():
            if prev.ip_address != curr.ip_address:
                changes.append(NodeChange(
                    prev.node_address, NodeChangeType.IP_ADDRESS_CHANGED,
                    (prev.ip_address, curr.ip_address), node=curr
                ))

        return changes

    async def filter_changes(self, ch_list: List[NodeChange], settings: dict) -> List[NodeChange]:
        return await super().filter_changes(ch_list, settings)
