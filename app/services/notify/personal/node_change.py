import asyncio
import operator
from collections import defaultdict
from functools import reduce
from typing import List, NamedTuple

from services.jobs.fetch.base import INotified
from services.lib.depcont import DepContainer
from services.lib.texts import grouper
from services.lib.utils import class_logger, turn_dic_inside_out
from services.models.node_info import NodeSetChanges, NodeInfo, MapAddressToPrevAndCurrNode
from services.models.node_watchers import NodeWatcherStorage

DEFAULT_SLASH_THRESHOLD = 5
MAX_CHANGES_PER_MESSAGE = 10


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

        # 1. extract changes
        changes: List[NodeChange] = []
        changes += self._changes_churned_nodes(node_set_change.nodes_activated, is_in=True)
        changes += self._changes_churned_nodes(node_set_change.nodes_deactivated, is_in=False)
        changes += self._changes_of_version(prev_and_curr_node_map)
        changes += self._changes_of_slash(prev_and_curr_node_map)

        # changes += self._dbg_add_mock_changes(prev_and_curr_node_map)      # fixme: debug!

        # 2. get list of changed nodes
        all_changed_node_addresses = set(c.address for c in changes)

        # 3. get list of user who watch those nodes
        node_to_user = await self.watchers.all_users_for_many_nodes(all_changed_node_addresses)
        all_users = reduce(operator.or_, node_to_user.values()) if node_to_user else []

        if not all_users:
            return  # nobody is interested in those changes...

        user_changes = defaultdict(list)

        for change in changes:
            for user in node_to_user[change.address]:
                user_changes[user].append(change)

        for user, ch_list in user_changes.items():
            groups = list(grouper(MAX_CHANGES_PER_MESSAGE, ch_list))
            for group in groups:
                text = '\n\n'.join(map(self._change_to_text, group))
                text = text.strip()
                if text:
                    asyncio.create_task(self.deps.broadcaster.safe_send_message(user, text))
                # await self.deps.bot.send_message(user, text)  # todo: empower the spam machine!

    def _change_to_text(self, c: NodeChange):
        if c.type == NodeChangeType.SLASHING:
            old, new = c.data
            # todo: loc.format message!
            return f'Your node <pre>{(c.address[-4:])}</pre> slashed <b>{new - old}</b> pts!'
        return ''

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

    @staticmethod
    def _dbg_add_mock_changes(pc_node_map: MapAddressToPrevAndCurrNode):
        return [NodeChange(addr, NodeChangeType.SLASHING, (curr.slash_points, curr.slash_points + 10)) for
                addr, (prev, curr) in pc_node_map.items()]

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
