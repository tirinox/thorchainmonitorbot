import asyncio
import operator
from collections import defaultdict
from functools import reduce
from typing import List, NamedTuple

from semver import VersionInfo

from services.jobs.fetch.base import INotified
from services.jobs.fetch.thormon import ThorMonWSSClient, ThorMonAnswer
from services.lib.depcont import DepContainer
from services.lib.texts import grouper
from services.lib.utils import class_logger
from services.models.node_info import NodeSetChanges, NodeInfo, MapAddressToPrevAndCurrNode
from services.models.node_watchers import NodeWatcherStorage
from services.notify.types.version_notify import KnownVersionStorage

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
    single_per_user: bool = False


class NodeChangePersonalNotifier(INotified):
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = class_logger(self)
        self.watchers = NodeWatcherStorage(deps)
        self.thor_mon = ThorMonWSSClient(deps.cfg.network_id)
        self.prev_thormon_state = ThorMonAnswer.empty()
        self.version_store = KnownVersionStorage(deps, context_name='personal')

    async def prepare(self):
        self.thor_mon.subscribe(self)
        asyncio.create_task(self.thor_mon.listen_forever())

    async def on_data(self, sender, data):
        if isinstance(data, NodeSetChanges):
            asyncio.create_task(self._handle_node_churn_bg_job(data))  # long-running job goes to the background!
        elif isinstance(data, ThorMonAnswer):
            asyncio.create_task(self._handle_thormon_message_bg_job(data))  # long-running job goes to the background!

    async def _handle_thormon_message_bg_job(self, data: ThorMonAnswer):
        changes = []
        await self._cast_messages_for_changes(changes)

    async def _handle_node_churn_bg_job(self, node_set_change: NodeSetChanges):
        prev_and_curr_node_map = node_set_change.prev_and_curr_node_map

        # 1. extract changes
        changes = []
        changes += self._changes_churned_nodes(node_set_change.nodes_activated, is_in=True)
        changes += self._changes_churned_nodes(node_set_change.nodes_deactivated, is_in=False)
        changes += self._changes_of_version(prev_and_curr_node_map)
        changes += self._changes_of_slash(prev_and_curr_node_map)
        changes += await self._changes_of_detected_new_version(node_set_change)
        # changes += self._dbg_add_mock_changes(prev_and_curr_node_map)      # fixme: debug!

        await self._cast_messages_for_changes(changes)

    async def _cast_messages_for_changes(self, changes: List[NodeChange]):
        if not changes:
            return

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
                this_user = user_changes[user]
                if change.single_per_user and any(c.type == change.type for c in this_user):
                    continue
                this_user.append(change)

        for user, ch_list in user_changes.items():
            groups = list(grouper(MAX_CHANGES_PER_MESSAGE, ch_list))  # split to several messages
            for group in groups:
                text = '\n\n'.join(map(self._format_change_to_text, group))
                text = text.strip()
                if text:
                    asyncio.create_task(self.deps.broadcaster.safe_send_message(user, text))

    def _format_change_to_text(self, c: NodeChange):
        # todo: loc.format message!
        message = ''
        if c.type == NodeChangeType.SLASHING:
            old, new = c.data
            message = f'Your node <pre>{(c.address[-4:])}</pre> slashed <b>{new - old}</b> pts!'
        elif c.type == NodeChangeType.VERSION_CHANGED:
            old, new = c.data
            message = f'Your node <pre>{(c.address[-4:])}</pre> version from <b>{old}</b> to <b>{new}</b>!'
        elif c.type == NodeChangeType.NEW_VERSION_DETECTED:
            message = f'New version detected! <b>{c.data}</b>! Consider upgrading!'
        return message

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
#  7. (from cable) went online!
#  8. block height is not increasing
#  9. block height is not increasing on CHAIN?!
#  10. your node churned in / out
#  11. your node became a candidate for churn in (dropped?)
#  12. account txs (comes from native TX scanner (to implement))
