from typing import List

from services.lib.depcont import DepContainer
from services.models.node_info import MapAddressToPrevAndCurrNode, NodeEventType, NodeEvent
from services.notify.personal.helpers import BaseChangeTracker, NodeOpSetting


class IpAddressTracker(BaseChangeTracker):
    def __init__(self, deps: DepContainer):
        self.deps = deps

    async def get_all_changes(self, pc_node_map: MapAddressToPrevAndCurrNode) -> List[NodeEvent]:
        changes = []
        for a, (prev, curr) in pc_node_map.items():
            if prev.ip_address != curr.ip_address:
                changes.append(NodeEvent(
                    prev.node_address, NodeEventType.IP_ADDRESS_CHANGED,
                    (prev.ip_address, curr.ip_address), node=curr, tracker=self
                ))

        return changes

    async def is_event_ok(self, event: NodeEvent, user_id, settings: dict) -> bool:
        return bool(settings.get(NodeOpSetting.IP_ADDRESS_ON, True))