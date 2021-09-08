import asyncio
import operator
from collections import defaultdict
from functools import reduce
from typing import List

from localization import LocalizationManager
from services.jobs.fetch.base import INotified
from services.jobs.fetch.thormon import ThorMonWSSClient
from services.lib.date_utils import HOUR, MINUTE
from services.models.thormon import ThorMonAnswer
from services.lib.depcont import DepContainer
from services.lib.texts import grouper
from services.lib.utils import class_logger
from services.models.node_info import NodeSetChanges, MapAddressToPrevAndCurrNode, NodeChangeType, NodeChange
from services.models.node_watchers import NodeWatcherStorage
from services.notify.personal.chain_height import ChainHeightTracker
from services.notify.personal.churning import NodeChurnTracker
from services.notify.personal.ip_addr import IpAddressTracker
from services.notify.personal.models import BaseChangeTracker
from services.notify.personal.node_online import NodeOnlineTracker
from services.notify.personal.slashing import SlashPointTracker
from services.notify.personal.telemetry import NodeTelemetryDatabase
from services.notify.personal.versions import VersionTracker

DEFAULT_SLASH_THRESHOLD = 5
MAX_CHANGES_PER_MESSAGE = 10

TELEMETRY_MAX_HISTORY_DURATION = HOUR
TELEMETRY_TOLERANCE = MINUTE
TELEMETRY_MAX_POINTS = 5_000


class NodeChangePersonalNotifier(INotified):
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = class_logger(self)
        self.watchers = NodeWatcherStorage(deps)
        self.thor_mon = ThorMonWSSClient(deps.cfg.network_id)
        self.telemetry_db = NodeTelemetryDatabase(deps)

        # trackers
        self.online_tracker = NodeOnlineTracker(deps)
        self.chain_height_tracker = ChainHeightTracker(deps)
        self.version_tracker = VersionTracker(deps)
        self.ip_address_tracker = IpAddressTracker(deps)
        self.churn_tracker = NodeChurnTracker(deps)
        self.slash_tracker = SlashPointTracker(deps)

    async def prepare(self):
        self.thor_mon.subscribe(self)
        asyncio.create_task(self.thor_mon.listen_forever())

    async def on_data(self, sender, data):
        if isinstance(data, NodeSetChanges):
            asyncio.create_task(self._handle_node_churn_bg_job(data))  # long-running job goes to the background!
        elif isinstance(data, ThorMonAnswer):
            asyncio.create_task(self._handle_thormon_message_bg_job(data))  # long-running job goes to the background!

    async def _handle_thormon_message_bg_job(self, data: ThorMonAnswer):
        await self.telemetry_db.write_telemetry(data)

        changes = []
        for node in data.nodes:
            telemetry_data = await NodeTelemetryDatabase(self.deps).read_telemetry(
                node.node_address, max_ago_sec=TELEMETRY_MAX_HISTORY_DURATION,
                tolerance=TELEMETRY_TOLERANCE, n_points=TELEMETRY_MAX_POINTS
            )
            changes += await self.online_tracker.get_node_changes(node.node_address, telemetry_data)
            changes += await self.chain_height_tracker.get_node_changes(node.node_address, telemetry_data)
        await self._cast_messages_for_changes(changes)

    async def _handle_node_churn_bg_job(self, node_set_change: NodeSetChanges):
        prev_and_curr_node_map = node_set_change.prev_and_curr_node_map

        changes = []
        changes += await self.churn_tracker.get_all_changes(node_set_change)
        changes += await self.version_tracker.get_all_changes(node_set_change)
        changes += await self.slash_tracker.get_all_changes(prev_and_curr_node_map)
        changes += await self.ip_address_tracker.get_all_changes(prev_and_curr_node_map)

        # changes += self._dbg_add_mock_changes(prev_and_curr_node_map)

        await self._cast_messages_for_changes(changes)

    async def _cast_messages_for_changes(self, changes: List[NodeChange]):
        if not changes:
            return

        self.logger.info(f'Casting Node changes ({len(changes)} items)')

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

        loc_man: LocalizationManager = self.deps.loc_man

        for user, ch_list in user_changes.items():
            loc = await loc_man.get_from_db(user, self.deps.db)

            settings = await self.watchers.get_user_settings(user)

            # filter changes according to the user's setting
            filtered_change_list = await self._filter_changes(ch_list, settings)

            groups = list(grouper(MAX_CHANGES_PER_MESSAGE, filtered_change_list))  # split to several messages

            self.logger.info(f'Sending personal notifications to user: {user}: '
                             f'{len(ch_list)} changes grouped to {len(groups)} groups...')

            for group in groups:
                text = '\n\n'.join(loc.notification_text_for_node_op_changes(c) for c in group)
                text = text.strip()
                if text:
                    asyncio.create_task(self.deps.broadcaster.safe_send_message(user, text))

    async def _filter_changes(self, ch_list: List[NodeChange], settings: dict) -> List[NodeChange]:
        trackers = (
            self.online_tracker,
            self.chain_height_tracker,
            self.slash_tracker,
            self.churn_tracker,
            self.ip_address_tracker,
            self.version_tracker
        )
        for tracker in trackers:
            tracker: BaseChangeTracker
            ch_list = await tracker.filter_changes(ch_list, settings)
        return ch_list

    @staticmethod
    def _dbg_add_mock_changes(pc_node_map: MapAddressToPrevAndCurrNode):
        return [
            NodeChange(addr, NodeChangeType.SLASHING, (curr.slash_points, curr.slash_points + 10)) for
            addr, (prev, curr) in pc_node_map.items()
        ]

# Changes?
#  1. (inst) version update
#  2. (inst) new version detected, consider upgrade?
#  3. (inst) slash point increase (over threshold)  .
#  4. bond changes (over threshold) e.g. > 1% in hour??
#  5. (inst) ip address change?
#  6. (from cable) went offline/online? (time from in this status?)
#  8. block height is not increasing
#  9. block height is not increasing on CHAIN?!
#  10. (inst) your node churned in / out
#  11. account txs (comes from native TX scanner (to implement))
