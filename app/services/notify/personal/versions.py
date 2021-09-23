from typing import List

from services.lib.depcont import DepContainer
from services.models.node_info import MapAddressToPrevAndCurrNode, NodeSetChanges, NodeEventType, NodeEvent
from services.notify.personal.helpers import BaseChangeTracker
from services.notify.types.version_notify import KnownVersionStorage


class VersionTracker(BaseChangeTracker):
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.version_store = KnownVersionStorage(deps, context_name='personal')

    async def get_all_changes(self, node_set_change: NodeSetChanges) -> List[NodeEvent]:
        changes = []
        changes += self._changes_of_version(node_set_change.prev_and_curr_node_map)
        changes += await self._changes_of_detected_new_version(node_set_change)
        return changes

    # todo: Event: The NodeOp majority upgraded to the new version! hurry up!

    @staticmethod
    def _changes_of_version(pc_node_map: MapAddressToPrevAndCurrNode):
        for a, (prev, curr) in pc_node_map.items():
            if prev.version != curr.version:
                yield NodeEvent(
                    prev.node_address, NodeEventType.VERSION_CHANGED,
                    (prev.version, curr.version),
                    node=curr
                )

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
                changes.append(NodeEvent(
                    node.node_address,
                    NodeEventType.NEW_VERSION_DETECTED,
                    new_version, single_per_user=True,
                    node=node
                ))
        return changes

    async def filter_events(self, ch_list: List[NodeEvent], settings: dict) -> List[NodeEvent]:
        return await super().filter_events(ch_list, settings)
