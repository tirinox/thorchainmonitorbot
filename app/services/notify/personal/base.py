import abc
import asyncio
from abc import ABC
from collections import defaultdict

from services.lib.delegates import INotified
from services.lib.depcont import DepContainer
from services.lib.settings_manager import SettingsManager
from services.lib.utils import WithLogger, grouper
from services.notify.channel import ChannelDescriptor, BoardMessage
from services.notify.personal.helpers import GeneralSettings


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
            users_for_event = set(self.get_users_from_event(ev, address_to_user))

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

    async def filter_events(self, event_list, user, settings):
        # no operation
        return event_list

    @abc.abstractmethod
    def get_users_from_event(self, ev, address_to_user):
        ...

    @abc.abstractmethod
    async def generate_messages(self, loc, group, settings, user, user_watch_addy_list, name_map):
        """
        Example:
        messages = [loc.notification_text_...(ev, my_addresses, name_map) for ev in group]
        return messages
        """
        pass
