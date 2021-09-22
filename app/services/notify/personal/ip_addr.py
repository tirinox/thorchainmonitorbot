from typing import List

from services.lib.depcont import DepContainer
from services.models.node_info import MapAddressToPrevAndCurrNode, NodeEventType, NodeEvent
from services.notify.personal.helpers import BaseChangeTracker


class IpAddressTracker(BaseChangeTracker):
    def __init__(self, deps: DepContainer):
        self.deps = deps

    async def get_all_changes(self, pc_node_map: MapAddressToPrevAndCurrNode) -> List[NodeEvent]:
        changes = []
        for a, (prev, curr) in pc_node_map.items():
            if prev.ip_address != curr.ip_address:
                changes.append(NodeEvent(
                    prev.node_address, NodeEventType.IP_ADDRESS_CHANGED,
                    (prev.ip_address, curr.ip_address), node=curr
                ))

        return changes

    async def filter_events(self, ch_list: List[NodeEvent], settings: dict) -> List[NodeEvent]:
        return await super().filter_events(ch_list, settings)
