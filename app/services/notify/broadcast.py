import asyncio
import random
import time
from typing import List

from localization import LocalizationManager
from services.lib.depcont import DepContainer
from services.lib.utils import copy_photo, class_logger
from services.notify.channel import Messengers, ChannelDescriptor, CHANNEL_INACTIVE, MessageType, BoardMessage
from services.notify.user_registry import UserRegistry


class Broadcaster:
    EXTRA_RETRY_DELAY = 0.1

    def __init__(self, d: DepContainer):
        self.deps = d

        self._broadcast_lock = asyncio.Lock()
        self._rng = random.Random(time.time())
        self.logger = class_logger(self)

        self._user_registry = UserRegistry(self.deps.db)

        # public channels
        self.channels = list(ChannelDescriptor.from_json(j) for j in self.deps.cfg.get_pure('channels'))

    def get_channels(self, channel_type):
        return [c for c in self.channels if c.type == channel_type]

    async def get_subscribed_channels(self):
        return await self.deps.gen_alert_settings_proc.get_general_alerts_channels(self.deps.settings_manager)

    async def notify_preconfigured_channels(self, f, *args, **kwargs):
        subscribed_channels = await self.get_subscribed_channels()
        all_channels = self.channels + subscribed_channels
        self.logger.info(f'Total channels: {len(all_channels)}: {len(self.channels)} + {len(subscribed_channels)}')

        loc_man: LocalizationManager = self.deps.loc_man
        user_lang_map = {
            channels.channel_id: loc_man.get_from_lang(channels.lang)
            for channels in all_channels
        }

        if not callable(f):  # if constant
            await self.broadcast(all_channels, f, *args, **kwargs)
            return

        async def message_gen(chat_id):
            locale = user_lang_map[chat_id]
            if hasattr(locale, f.__name__):
                loc_f = getattr(locale, f.__name__)
                call_args = args
            else:
                loc_f = f
                call_args = [locale, *args]

            if asyncio.iscoroutinefunction(loc_f):
                return await loc_f(*call_args, **kwargs)
            else:
                return loc_f(*call_args, **kwargs)

        await self.broadcast(all_channels, message_gen)

    async def _handle_bad_user(self, channel_info):
        self.logger.info(f'{channel_info} became inactive!')
        channel_id = channel_info.channel_id
        if channel_id:
            await self.deps.settings_manager.make_inactive(channel_id)
            await self._user_registry.remove_users(channel_id)

    # noinspection PyBroadException
    async def safe_send_message(self, channel_info: ChannelDescriptor,
                                message: BoardMessage, **kwargs) -> bool:
        result = False
        try:
            if isinstance(message, str):
                message = BoardMessage(message)

            if channel_info.type not in Messengers.SUPPORTED:
                self.logger.error(f'Unsupported channel type: {channel_info.type}!')
            else:
                channel_id = channel_info.channel_id
                messenger = self.deps.get_messenger(channel_info.type)
                if messenger is not None:
                    result = await messenger.safe_send_message(channel_id, message, **kwargs)
                    if result == CHANNEL_INACTIVE:
                        await self._handle_bad_user(channel_info)
                else:
                    self.logger.error(f'{channel_info.type} bot is disabled!')
        except Exception:
            self.logger.exception('We are still safe!', stack_info=True)

        return result

    @staticmethod
    async def _form_message(text, channel_info: ChannelDescriptor, **kwargs) -> BoardMessage:
        if isinstance(text, BoardMessage):
            return text
        elif isinstance(text, str):
            return BoardMessage(text)
        elif callable(text):
            b_message = await text(channel_info.channel_id, **kwargs)
            if isinstance(b_message, BoardMessage):
                if b_message.message_type is MessageType.PHOTO:
                    # noinspection PyTypeChecker
                    b_message.photo = copy_photo(b_message.photo)
                return b_message
            else:
                return BoardMessage(str(b_message))
        else:
            return BoardMessage(str(text))

    async def broadcast(self, channels: List[ChannelDescriptor], message, delay=0.075, **kwargs) -> int:
        async with self._broadcast_lock:
            count = 0

            try:
                for channel_info in channels:
                    # make from any message a BoardMessage
                    b_message = await self._form_message(message, channel_info, **kwargs)
                    if b_message.empty:
                        continue

                    send_results = await self.safe_send_message(
                        channel_info, b_message,
                        disable_web_page_preview=True,
                        disable_notification=False, **kwargs)

                    if send_results is True:
                        count += 1

                    await asyncio.sleep(delay)  # 10 messages per second (Limit: 30 messages per second)
            finally:
                self.logger.info(f"{count} messages successful sent (of {len(channels)})")

            return count
