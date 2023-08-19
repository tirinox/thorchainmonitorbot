from typing import List

from services.lib.depcont import DepContainer
from services.models.node_info import NodeEventType, NodeEvent
from services.notify.personal.helpers import BaseChangeTracker, NodeOpSetting


class IpAddressTracker(BaseChangeTracker):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

    async def get_events_unsafe(self) -> List[NodeEvent]:
        changes = []
        for a, (prev, curr) in self.prev_and_curr_node_map.items():
            if prev.ip_address != curr.ip_address:
                changes.append(NodeEvent(
                    prev.node_address, NodeEventType.IP_ADDRESS_CHANGED,
                    (prev.ip_address, curr.ip_address), node=curr, tracker=self
                ))

        return changes

    async def is_event_ok(self, event: NodeEvent, user_id, settings: dict) -> bool:
        return bool(settings.get(NodeOpSetting.IP_ADDRESS_ON, True))