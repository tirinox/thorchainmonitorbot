import asyncio
import operator
from collections import defaultdict
from functools import reduce
from typing import List, Optional

from localization import LocalizationManager
from services.jobs.fetch.base import INotified
from services.jobs.fetch.thormon import ThorMonWSSClient
from services.lib.date_utils import HOUR, MINUTE
from services.models.thormon import ThorMonAnswer
from services.lib.depcont import DepContainer
from services.lib.texts import grouper
from services.lib.utils import class_logger
from services.models.node_info import NodeSetChanges, MapAddressToPrevAndCurrNode, NodeEventType, NodeEvent
from services.models.node_watchers import NodeWatcherStorage
from services.notify.personal.bond import BondTracker
from services.notify.personal.chain_height import ChainHeightTracker
from services.notify.personal.churning import NodeChurnTracker
from services.notify.personal.ip_addr import IpAddressTracker
from services.notify.personal.helpers import BaseChangeTracker
from services.notify.personal.node_online import NodeOnlineTracker
from services.notify.personal.slashing import SlashPointTracker
from services.notify.personal.telemetry import NodeTelemetryDatabase
from services.notify.personal.user_data import UserDataCache
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
        self.bond_tracker = BondTracker(deps)

    async def prepare(self):
        self.thor_mon.subscribe(self)
        asyncio.create_task(self.thor_mon.listen_forever())

    async def on_data(self, sender, data):
        if isinstance(data, NodeSetChanges):  # from Churn Fetcher
            asyncio.create_task(self._handle_node_churn_bg_job(data))  # long-running job goes to the background!
        elif isinstance(data, ThorMonAnswer):  # from ThorMon
            asyncio.create_task(self._handle_thormon_message_bg_job(data))  # long-running job goes to the background!

    async def _handle_thormon_message_bg_job(self, data: ThorMonAnswer):
        await self.telemetry_db.write_telemetry(data)

        self.chain_height_tracker.estimate_block_height(data, maximum=True)

        user_cache = await UserDataCache.load(self.deps.db)
        self.logger.info(str(user_cache))

        events = []

        events += await self.online_tracker.get_events(data, user_cache)
        events += await self.chain_height_tracker.get_events(data, user_cache)

        for node in data.nodes:
            # fixme!
            telemetry_data = await NodeTelemetryDatabase(self.deps).read_telemetry(
                node.node_address, max_ago_sec=TELEMETRY_MAX_HISTORY_DURATION,
                tolerance=TELEMETRY_TOLERANCE, n_points=TELEMETRY_MAX_POINTS
            )
            events += await self.slash_tracker.get_node_events(node.node_address, telemetry_data)  # todo params

        await self._cast_messages_for_events(events)

        await user_cache.save(self.deps.db)

    async def _handle_node_churn_bg_job(self, node_set_change: NodeSetChanges):
        prev_and_curr_node_map = node_set_change.prev_and_curr_node_map

        events = []
        events += await self.churn_tracker.get_all_changes(node_set_change)
        events += await self.version_tracker.get_all_changes(node_set_change)
        events += await self.ip_address_tracker.get_all_changes(prev_and_curr_node_map)
        events += await self.bond_tracker.get_all_changes(prev_and_curr_node_map)

        await self._cast_messages_for_events(events)

    async def _cast_messages_for_events(self, events: List[NodeEvent]):
        if not events:
            return

        self.logger.info(f'Casting Node changes ({len(events)} items)')

        # 2. get list of changed nodes
        affected_node_addresses = set(c.address for c in events)

        # 3. get list of user who watch those nodes
        node_to_user = await self.watchers.all_users_for_many_nodes(affected_node_addresses)
        all_users = reduce(operator.or_, node_to_user.values()) if node_to_user else []

        if not all_users:
            return  # nobody is interested in those changes...

        user_events = defaultdict(list)
        for event in events:
            for user in node_to_user[event.address]:
                this_user = user_events[user]

                # single_per_user: skip all events of this kind if there was one before!
                if event.single_per_user and any(e.type == event.type for e in this_user):
                    continue

                this_user.append(event)

        loc_man: LocalizationManager = self.deps.loc_man

        # for every user
        for user, event_list in user_events.items():
            loc = await loc_man.get_from_db(user, self.deps.db)

            settings = await self.watchers.get_user_settings(user)

            # filter changes according to the user's setting
            filtered_change_list = await self._filter_events(event_list, user, settings)

            groups = list(grouper(MAX_CHANGES_PER_MESSAGE, filtered_change_list))  # split to several messages

            if groups:
                self.logger.info(f'Sending personal notifications to user: {user}: '
                                 f'{len(event_list)} changes grouped to {len(groups)} groups...')

            for group in groups:
                messages = [loc.notification_text_for_node_op_changes(c) for c in group]
                text = '\n\n'.join(m for m in messages if m)
                text = text.strip()
                if text:
                    asyncio.create_task(self.deps.broadcaster.safe_send_message(user, text))

    @staticmethod
    async def _filter_events(event_list: List[NodeEvent], user_id, settings: dict) -> List[NodeEvent]:
        results = []
        for event in event_list:
            # noinspection PyTypeChecker
            tracker: BaseChangeTracker = event.tracker
            if tracker and await tracker.is_event_ok(event, user_id, settings):
                results.append(event)
        return results

    @property
    def last_signal_sec_ago(self):
        return self.thor_mon.last_signal_sec_ago
