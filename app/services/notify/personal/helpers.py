import abc
import asyncio
from abc import ABC
from collections import defaultdict
from typing import List, Any, Tuple, Optional

from services.lib.date_utils import now_ts
from services.lib.delegates import INotified
from services.lib.depcont import DepContainer
from services.lib.settings_manager import SettingsManager
from services.lib.utils import class_logger, WithLogger, grouper
from services.models.node_info import NodeEvent, MapAddressToPrevAndCurrNode, NodeSetChanges
from services.notify.channel import BoardMessage, ChannelDescriptor
from services.notify.personal.user_data import UserDataCache

STANDARD_INTERVALS = [
    '2m',
    '5m',
    '15m',
    '30m',
    '60m',
    '2h',
    '6h',
    '12h',
    '24h',
    '3d',
]


class NodeOpSetting:
    IP_ADDRESS_ON = 'nop:ip:on'
    VERSION_ON = 'nop:version:on'
    NEW_VERSION_ON = 'nop:new_v:on'
    BOND_ON = 'nop:bond:on'
    OFFLINE_ON = 'nop:offline:on'
    OFFLINE_INTERVAL = 'nop:offline:interval'
    CHAIN_HEIGHT_ON = 'nop:height:on'
    CHAIN_HEIGHT_INTERVAL = 'nop:height:interval'
    CHURNING_ON = 'nop:churning:on'
    SLASH_ON = 'nop:slash:on'
    SLASH_THRESHOLD = 'nop:slash:threshold'
    SLASH_PERIOD = 'nop:slash:period'
    PAUSE_ALL_ON = 'nop:pause_all:on'

    NODE_PRESENCE = 'nop:presence:on'  # new


class GeneralSettings:
    INACTIVE = '_inactive'

    GENERAL_ALERTS = 'gen:alerts'
    PRICE_DIV_ALERTS = 'personal:price-div'
    VAR_PRICE_DIV_LAST_VALUE = 'personal:price-div:$last'
    LANGUAGE = 'lang'
    BALANCE_TRACK = 'personal:balance-track'


class Props:
    KEY_ADDRESSES = 'addresses'

    PROP_TRACK_BALANCE = 'track_balance'
    PROP_ADDRESS = 'address'
    PROP_CHAIN = 'chain'
    PROP_MIN_LIMIT = 'min'
    PROP_TRACK_BOND = 'bond_prov'


class BaseChangeTracker:
    def __init__(self):
        self.logger = class_logger(self)

        self.user_cache: Optional[UserDataCache] = None
        self.prev_and_curr_node_map: MapAddressToPrevAndCurrNode = {}
        self.node_set_change: Optional[NodeSetChanges] = None

    async def is_event_ok(self, event: NodeEvent, user_id, settings: dict) -> bool:
        return True

    async def get_events(self) -> List[NodeEvent]:
        try:
            return await self.get_events_unsafe()
        except Exception:
            self.logger.exception('Failed to get events!', exc_info=True)
            return []

    async def get_events_unsafe(self) -> List[NodeEvent]:
        raise NotImplemented


def get_points_at_time_points(data: List[Tuple[float, Any]], ago_sec_list: list):
    if not ago_sec_list or not data:
        return {}

    now = now_ts()
    results = {}
    ago_list_pos = 0
    for ts, data in reversed(data):  # from new to older
        current_ago = ago_sec_list[ago_list_pos]
        if ts < now - current_ago:
            results[current_ago] = ts, data
            ago_list_pos += 1
            if ago_list_pos >= len(ago_sec_list):
                break
    return results


class BasePersonalNotifier(INotified, WithLogger, ABC):
    def __init__(self, d: DepContainer, watcher, max_events_per_message=3):
        super().__init__()
        self.deps = d
        self.watcher = watcher
        self.max_events_per_message = max_events_per_message

    async def _send_message(self, messages, settings, user):
        platform = SettingsManager.get_platform(settings)

        text = '\n\n'.join(m for m in messages if m)
        text = text.strip()
        if text:
            task = self.deps.broadcaster.safe_send_message_rate(
                ChannelDescriptor(platform, user),
                BoardMessage(text),
                disable_web_page_preview=True
            )
            asyncio.create_task(task)

    async def group_and_send_messages(self, addresses, events):
        if not addresses:
            return

        address_to_user = await self.watcher.all_users_for_many_nodes(addresses)
        all_affected_users = self.watcher.all_affected_users(address_to_user)
        user_to_address = self.watcher.reverse(address_to_user)

        if not all_affected_users:
            return

        # Sort events by user
        user_events = defaultdict(list)
        for ev in events:
            users_for_event = set(address_to_user.get(ev.from_addr)) | set(address_to_user.get(ev.to_addr))

            for user in users_for_event:
                user_events[user].append(ev)

        # Load THORNames
        name_map = await self.deps.name_service.safely_load_thornames_from_address_set(addresses)

        # Load their settings
        settings_dic = await self.deps.settings_manager.get_settings_multi(user_events.keys())

        for user, event_list in user_events.items():
            settings = settings_dic.get(user, {})

            if bool(settings.get(GeneralSettings.INACTIVE, False)):
                continue  # paused

            # filter events according to the user's preferences
            filtered_event_list = await self.filter_events(event_list, user, settings)

            # split to several messages
            groups = list(grouper(self.max_events_per_message, filtered_event_list))

            if groups:
                self.logger.info(f'Sending personal notifications to user: {user}: '
                                 f'{len(event_list)} events grouped to {len(groups)} groups...')

                loc = await self.deps.loc_man.get_from_db(user, self.deps.db)

                user_watch_addy_list = user_to_address.get(user, [])

                for group in groups:
                    if group:
                        messages = await self.generate_messages(
                            loc, group, settings, user, user_watch_addy_list, name_map)
                        await self._send_message(messages, settings, user)

    @abc.abstractmethod
    async def filter_events(self, event_list, user, settings):
        return True

    @abc.abstractmethod
    async def generate_messages(self, loc, group, settings, user, user_watch_addy_list, name_map):
        """
        Example:
        messages = [loc.notification_text_...(ev, my_addresses, name_map) for ev in group]
        return messages
        """
        pass
