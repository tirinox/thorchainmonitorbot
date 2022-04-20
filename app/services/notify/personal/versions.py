from typing import List

from services.lib.depcont import DepContainer
from services.models.node_info import MapAddressToPrevAndCurrNode, NodeSetChanges, NodeEventType, NodeEvent
from services.notify.personal.helpers import BaseChangeTracker, NodeOpSetting
from services.notify.types.version_notify import KnownVersionStorage


class VersionTracker(BaseChangeTracker):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.version_store = KnownVersionStorage(deps, context_name='personal')

    async def get_events_unsafe(self) -> List[NodeEvent]:
        changes = []
        changes += self._changes_of_version(self.node_set_change.prev_and_curr_node_map)
        changes += await self._changes_of_detected_new_version(self.node_set_change)

        # # fixme: debug
        # changes.append(NodeEvent(
        #     'thor1tmutepp5q8cta58arlcv8mm9jer7k8xs73cd89',
        #     NodeEventType.NEW_VERSION_DETECTED, ('1.2.3', '3.4.5'), single_per_user=True,
        # ))

        return changes

    # todo: Event: The NodeOp majority upgraded to the new version! hurry up!

    def _changes_of_version(self, pc_node_map: MapAddressToPrevAndCurrNode):
        for a, (prev, curr) in pc_node_map.items():
            if prev.version != curr.version:
                yield NodeEvent(
                    prev.node_address, NodeEventType.VERSION_CHANGED,
                    (prev.version, curr.version),
                    node=curr, tracker=self
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
                    node=node, tracker=self
                ))
        return changes

    async def is_event_ok(self, event: NodeEvent, user_id, settings: dict) -> bool:
        if event.type == NodeEventType.NEW_VERSION_DETECTED and bool(settings.get(NodeOpSetting.NEW_VERSION_ON, True)):
            return True

        if event.type == NodeEventType.VERSION_CHANGED and bool(settings.get(NodeOpSetting.VERSION_ON, True)):
            return True

        return False
