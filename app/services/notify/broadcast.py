import asyncio
import logging
import random
import time
from typing import Iterable

from aiogram.utils import exceptions

from localization import LocalizationManager
from services.lib.depcont import DepContainer
from services.lib.texts import MessageType, BoardMessage


class Broadcaster:
    KEY_USERS = 'thbot_users'

    def __init__(self, d: DepContainer):
        self.bot = d.bot
        self.cfg = d.cfg
        self.db = d.db

        self._broadcast_lock = asyncio.Lock()
        self._rng = random.Random(time.time())
        self.logger = logging.getLogger('broadcast')

    def telegram_chats_from_config(self, loc_man: LocalizationManager):
        channels = self.cfg.telegram.channels
        return {
            chan['name']: loc_man.get_from_lang(chan['lang']) for chan in channels if chan['type'] == 'telegram'
        }

    async def notify_preconfigured_channels(self, loc_man: LocalizationManager, f, *args, **kwargs):
        user_lang_map = self.telegram_chats_from_config(loc_man)

        async def message_gen(chat_id):
            locale = user_lang_map[chat_id]
            loc_f = getattr(locale, f.__name__)
            if asyncio.iscoroutinefunction(loc_f):
                return await loc_f(*args, **kwargs)
            else:
                return loc_f(*args, **kwargs)

        await self.broadcast(user_lang_map.keys(), message_gen)

    @staticmethod
    def remove_bad_args(kwargs, dis_web_preview=False, dis_notification=False):
        if dis_web_preview:
            if 'disable_web_page_preview' in kwargs:
                del kwargs['disable_web_page_preview']
        if dis_notification:
            if 'disable_notification' in kwargs:
                del kwargs['disable_notification']
        return kwargs

    async def _send_message(self, chat_id, text, message_type=MessageType.TEXT, *args, **kwargs) -> bool:
        """
        Safe messages sender
        :param chat_id:
        :param text:
        :param disable_notification:
        :return:
        """
        try:
            if message_type == MessageType.TEXT:
                await self.bot.send_message(chat_id, text, *args, **kwargs)
            elif message_type == MessageType.STICKER:
                kwargs = self.remove_bad_args(kwargs, dis_web_preview=True)
                await self.bot.send_sticker(chat_id, sticker=text, *args, **kwargs)
            elif message_type == MessageType.PHOTO:
                kwargs = self.remove_bad_args(kwargs, dis_web_preview=True)
                await self.bot.send_photo(chat_id, caption=text, *args, **kwargs)
        except exceptions.BotBlocked:
            self.logger.error(f"Target [ID:{chat_id}]: blocked by user")
        except exceptions.ChatNotFound:
            self.logger.error(f"Target [ID:{chat_id}]: invalid user ID")
        except exceptions.RetryAfter as e:
            self.logger.error(f"Target [ID:{chat_id}]: Flood limit is exceeded. Sleep {e.timeout} seconds.")
            await asyncio.sleep(e.timeout + 0.1)
            return await self._send_message(chat_id, text, message_type=message_type, *args, **kwargs)  # Recursive call
        except exceptions.UserDeactivated:
            self.logger.error(f"Target [ID:{chat_id}]: user is deactivated")
        except exceptions.TelegramAPIError:
            self.logger.exception(f"Target [ID:{chat_id}]: failed")
            return True  # tg error is not the reason to exclude the user
        else:
            self.logger.info(f"Target [ID:{chat_id}]: success")
            return True
        return False

    def sort_and_shuffle_chats(self, chat_ids):
        numeric_ids = [i for i in chat_ids if isinstance(i, int)]
        non_numeric_ids = [i for i in chat_ids if not isinstance(i, int)]

        user_dialogs = [i for i in numeric_ids if i > 0]
        multi_chats = [i for i in numeric_ids if i < 0]
        self._rng.shuffle(user_dialogs)
        self._rng.shuffle(multi_chats)

        return non_numeric_ids + multi_chats + user_dialogs

    async def broadcast(self, chat_ids: Iterable, message, delay=0.075,
                        message_type=MessageType.TEXT, *args, **kwargs) -> int:
        """
        Simple broadcaster
        :param message_type: see MessageType
        :param chat_ids: list of chat ids
        :param message: message string or sticker id
        :param delay: anti-spam delay
        :param args:
        :param kwargs:
        :return: Count of messages sent
        """
        async with self._broadcast_lock:
            count = 0
            bad_ones = []

            try:
                chat_ids = self.sort_and_shuffle_chats(chat_ids)

                for chat_id in chat_ids:
                    extra = {}
                    if isinstance(message, str):
                        text = message
                    elif callable(message):
                        message = await message(chat_id, *args, **kwargs)
                        if isinstance(message, BoardMessage):
                            message_type = message.message_type
                            if message.message_type is MessageType.PHOTO:
                                extra['photo'] = message.photo
                            text = message.text
                        else:
                            text = message

                    if text or 'photo' in extra:
                        if await self._send_message(chat_id, text, message_type=message_type,
                                                    disable_web_page_preview=True,
                                                    disable_notification=False, **extra):
                            count += 1
                        else:
                            bad_ones.append(chat_id)
                        await asyncio.sleep(delay)  # 10 messages per second (Limit: 30 messages per second)

                await self.remove_users(bad_ones)
            finally:
                self.logger.info(f"{count} messages successful sent (of {len(chat_ids)})")

            return count

    async def register_user(self, chat_id):
        chat_id = str(int(chat_id))
        r = await self.db.get_redis()
        await r.sadd(self.KEY_USERS, chat_id)

    async def remove_users(self, idents):
        idents = [str(int(i)) for i in idents]
        if idents:
            r = await self.db.get_redis()
            await r.srem(self.KEY_USERS, *idents)

    async def all_users(self):
        r = await self.db.get_redis()
        items = await r.smembers(self.KEY_USERS)
        return [int(it) for it in items]
