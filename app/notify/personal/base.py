import abc
import asyncio
from abc import ABC
from collections import defaultdict

from lib.delegates import INotified
from lib.depcont import DepContainer
from lib.logs import WithLogger
from lib.settings_manager import SettingsManager, SettingsContext
from lib.utils import grouper
from notify.channel import ChannelDescriptor, BoardMessage


class BasePersonalNotifier(INotified, WithLogger, ABC):
    def __init__(self, d: DepContainer, watcher, max_events_per_message=3):
        super().__init__()
        self.deps = d
        self.watcher = watcher
        self.max_events_per_message = max_events_per_message

    async def _send_message(self, message, settings, user, msg_type):
        platform = SettingsManager.get_platform(settings)

        message = message.strip()
        if message:
            task = self.deps.broadcaster.safe_send_message_rate(
                ChannelDescriptor(platform, user),
                BoardMessage(message, msg_type=msg_type),
                disable_web_page_preview=True
            )
            asyncio.create_task(task)

    async def group_and_send_messages(self, addresses, events, glue='\n\n', msg_type='personal:generic'):
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
            users_for_event = self.get_users_from_event(ev, address_to_user)
            users_for_event = set(users_for_event or [])

            for user in users_for_event:
                user_events[user].append(ev)

        # Load THORNames
        name_map = await self.deps.name_service.safely_load_thornames_from_address_set(addresses)

        # Load their settings
        settings_dic = await self.deps.settings_manager.get_settings_multi(user_events.keys())

        for user, event_list in user_events.items():
            settings = settings_dic.get(user, {})

            if SettingsContext.is_inactive_s(settings):
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
                        local_ns = self.deps.name_service.get_local_service(user)
                        local_name_map = await local_ns.get_name_map()
                        name_map_for_user = name_map.joined_with(local_name_map)

                        message = await self.generate_message_text(
                            loc, group, settings, user, user_watch_addy_list, name_map_for_user)

                        if not isinstance(message, str):
                            message = glue.join(message)

                        await self._send_message(message, settings, user, msg_type)

    async def filter_events(self, event_list, user, settings):
        # no operation
        return event_list

    @abc.abstractmethod
    def get_users_from_event(self, ev, address_to_user):
        ...

    @abc.abstractmethod
    async def generate_message_text(self, loc, group, settings, user, user_watch_addy_list, name_map):
        """
        Example:
        messages = [loc.notification_text_...(ev, my_addresses, name_map) for ev in group]
        return messages
        """
        pass
