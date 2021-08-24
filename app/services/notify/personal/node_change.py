import asyncio
import operator
from functools import reduce
from typing import List, NamedTuple

from services.jobs.fetch.base import INotified
from services.lib.depcont import DepContainer
from services.lib.utils import class_logger
from services.models.node_info import NodeSetChanges, NodeInfo, MapAddressToPrevAndCurrNode
from services.models.node_watchers import NodeWatcherStorage

DEFAULT_SLASH_THRESHOLD = 5


class NodeChangeType:
    VERSION_CHANGED = 'version_change'
    NEW_VERSION_DETECTED = 'new_version'
    SLASHING = 'slashing'
    CHURNED_IN = 'churned_in'
    CHURNED_OUT = 'churned_out'
    # todo: add more types


class NodeChange(NamedTuple):
    address: str
    type: str
    data: object


class NodeChangePersonalNotifier(INotified):
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = class_logger(self)
        self.watchers = NodeWatcherStorage(self.deps)

    async def on_data(self, sender, changes: NodeSetChanges):
        asyncio.create_task(self._bg_job(changes))  # long-running job goes to the background!

    async def _bg_job(self, node_set_change: NodeSetChanges):
        prev_and_curr_node_map = node_set_change.prev_and_curr_node_map

        changes = []
        changes += self._changes_churned_nodes(node_set_change.nodes_activated, is_in=True)
        changes += self._changes_churned_nodes(node_set_change.nodes_deactivated, is_in=False)
        changes += self._changes_of_version(prev_and_curr_node_map)
        changes += self._changes_of_slash(prev_and_curr_node_map)

        all_changed_node_addresses = set(c.address for c in changes)

        user_to_node_maps = await self.watchers.all_users_for_many_nodes(all_changed_node_addresses)
        all_users = reduce(operator.and_, user_to_node_maps.keys()) if user_to_node_maps else []

        if not all_users:
            return  # nobody is interested in those changes...

        print('All users:', all_users)

        # 1. compare old and new?
        # 2. extract changes
        # 3. get list of changed nodes
        # 4. get list of user who watch those nodes
        # 5. for user in Watchers:
        #    for node in user.nodes:
        #     changes = changes[node.address]
        #     for change in changes:
        #        user.sendMessage(format(change))

    @staticmethod
    def _changes_churned_nodes(nodes: List[NodeInfo], is_in: bool) -> List[NodeChange]:
        return [
            NodeChange(
                n.node_address, NodeChangeType.CHURNED_IN if is_in else NodeChangeType.CHURNED_OUT, n
            ) for n in nodes
        ]

    @staticmethod
    def _changes_of_version(pc_node_map: MapAddressToPrevAndCurrNode):
        for a, (prev, curr) in pc_node_map.items():
            if prev.version != curr.version:
                yield NodeChange(prev.node_address, NodeChangeType.VERSION_CHANGED, (prev.version, curr.version))

    @staticmethod
    def _changes_of_slash(pc_node_map: MapAddressToPrevAndCurrNode):
        for a, (prev, curr) in pc_node_map.items():
            if prev.slash_points != curr.slash_points:
                yield NodeChange(prev.node_address, NodeChangeType.SLASHING, (prev.slash_points, curr.slash_points))

# Changes?
#  1. (inst) version update
#  2. (inst) new version detected, consider upgrade?
#  3. (inst) slash point increase (over threshold)  .
#  4. bond changes (over threshold) e.g. > 1% in hour??
#  5. ip address change?
#  6. (from cable) went offline?
#  7. (from cable)went online!
#  8. block height is not increasing
#  9. block height is not increasing on CHAIN?!
#  10. your node churned in / out
#  11. your node became a candidate for churn in (dropped?)
#  12. account txs (comes from native TX scanner (to implement))
