from typing import List

from services.lib.depcont import DepContainer
from services.models.node_info import NodeSetChanges, NodeInfo, NodeChangeType, NodeChange
from services.notify.personal.models import BaseChangeTracker


class NodeChurnTracker(BaseChangeTracker):
    def __init__(self, deps: DepContainer):
        self.deps = deps

    async def get_all_changes(self, node_set_change: NodeSetChanges) -> List[NodeChange]:
        changes = []
        changes += self._changes_churned_nodes(node_set_change.nodes_activated, is_in=True)
        changes += self._changes_churned_nodes(node_set_change.nodes_deactivated, is_in=False)
        return changes

    @staticmethod
    def _changes_churned_nodes(nodes: List[NodeInfo], is_in: bool) -> List[NodeChange]:
        return [
            NodeChange(
                n.node_address, NodeChangeType.CHURNING, is_in, node=n
            ) for n in nodes
        ]
