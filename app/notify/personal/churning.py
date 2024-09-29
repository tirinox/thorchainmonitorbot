from typing import List

from lib.depcont import DepContainer
from models.node_info import NodeInfo, NodeEventType, NodeEvent
from notify.personal.helpers import BaseChangeTracker, NodeOpSetting


class NodeChurnTracker(BaseChangeTracker):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

    async def get_events_unsafe(self) -> List[NodeEvent]:
        changes = []
        changes += self._changes_churned_nodes(self.node_set_change.nodes_activated, is_in=True)
        changes += self._changes_churned_nodes(self.node_set_change.nodes_deactivated, is_in=False)
        return changes

    def _changes_churned_nodes(self, nodes: List[NodeInfo], is_in: bool) -> List[NodeEvent]:
        return [
            NodeEvent(
                n.node_address, NodeEventType.CHURNING, is_in, node=n, tracker=self
            ) for n in nodes
        ]

    async def is_event_ok(self, event: NodeEvent, user_id, settings: dict) -> bool:
        return bool(settings.get(NodeOpSetting.CHURNING_ON, True))
