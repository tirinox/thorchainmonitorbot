from typing import List

from services.lib.depcont import DepContainer
from services.models.node_info import MapAddressToPrevAndCurrNode, NodeSetChanges, NodeChangeType, NodeChange
from services.notify.personal.models import BaseChangeTracker
from services.notify.types.version_notify import KnownVersionStorage


class VersionTracker(BaseChangeTracker):
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.version_store = KnownVersionStorage(deps, context_name='personal')

    async def get_all_changes(self, node_set_change: NodeSetChanges) -> List[NodeChange]:
        changes = []
        changes += self._changes_of_version(node_set_change.prev_and_curr_node_map)
        changes += await self._changes_of_detected_new_version(node_set_change)
        return changes

    @staticmethod
    def _changes_of_version(pc_node_map: MapAddressToPrevAndCurrNode):
        for a, (prev, curr) in pc_node_map.items():
            if prev.version != curr.version:
                yield NodeChange(prev.node_address, NodeChangeType.VERSION_CHANGED, (prev.version, curr.version))

    async def _changes_of_detected_new_version(self, c: NodeSetChanges):
        new_versions = c.new_versions
        if not new_versions:
            return []

        new_version = next(reversed(new_versions))

        if await self.version_store.is_version_known(new_version):
            return []

        await self.version_store.mark_as_known([new_version])

        changes = []
        for node in c.nodes_all:
            if node.parsed_version < new_version:
                changes.append(NodeChange(node.node_address,
                                          NodeChangeType.NEW_VERSION_DETECTED,
                                          new_version, single_per_user=True))
        return changes
