from typing import List

from services.lib.depcont import DepContainer
from services.models.node_info import NodeSetChanges, NodeInfo, NodeEventType, NodeEvent
from services.notify.personal.helpers import BaseChangeTracker


class NodeChurnTracker(BaseChangeTracker):
    def __init__(self, deps: DepContainer):
        self.deps = deps

    async def get_all_changes(self, node_set_change: NodeSetChanges) -> List[NodeEvent]:
        changes = []
        changes += self._changes_churned_nodes(node_set_change.nodes_activated, is_in=True)
        changes += self._changes_churned_nodes(node_set_change.nodes_deactivated, is_in=False)
        return changes

    @staticmethod
    def _changes_churned_nodes(nodes: List[NodeInfo], is_in: bool) -> List[NodeEvent]:
        return [
            NodeEvent(
                n.node_address, NodeEventType.CHURNING, is_in, node=n
            ) for n in nodes
        ]

    async def filter_events(self, ch_list: List[NodeEvent], settings: dict) -> List[NodeEvent]:
        return await super().filter_events(ch_list, settings)
