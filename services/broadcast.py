import asyncio
import logging
import random
import time

from aiogram import Bot
from aiogram.utils import exceptions

from services.config import DB

log = logging.getLogger('broadcast')


class Broadcaster:
    KEY_USERS = 'thbot_users'

    def __init__(self, bot: Bot, db: DB):
        self.bot = bot
        self._broadcast_lock = asyncio.Lock()
        self._rng = random.Random(time.time())
        self.db = db

    async def _send_message(self, chat_id: int, text: str, disable_notification: bool = False) -> bool:
        """
        Safe messages sender
        :param chat_id:
        :param text:
        :param disable_notification:
        :return:
        """
        try:
            await self.bot.send_message(chat_id, text,
                                        disable_notification=disable_notification,
                                        disable_web_page_preview=True)
        except exceptions.BotBlocked:
            log.error(f"Target [ID:{chat_id}]: blocked by user")
        except exceptions.ChatNotFound:
            log.error(f"Target [ID:{chat_id}]: invalid user ID")
        except exceptions.RetryAfter as e:
            log.error(f"Target [ID:{chat_id}]: Flood limit is exceeded. Sleep {e.timeout} seconds.")
            await asyncio.sleep(e.timeout + 0.1)
            return await self._send_message(chat_id, text, disable_notification)  # Recursive call
        except exceptions.UserDeactivated:
            log.error(f"Target [ID:{chat_id}]: user is deactivated")
        except exceptions.TelegramAPIError:
            log.exception(f"Target [ID:{chat_id}]: failed")
            return True  # tg error is not the reason to exlude the user
        else:
            log.info(f"Target [ID:{chat_id}]: success")
            return True
        return False

    def sort_and_shuffle_chats(self, chat_ids):
        user_dialogs = [i for i in chat_ids if i > 0]
        multi_chats = [i for i in chat_ids if i < 0]
        self._rng.shuffle(user_dialogs)
        self._rng.shuffle(multi_chats)
        return multi_chats + user_dialogs

    async def broadcast(self, chat_ids, message, delay=0.075) -> int:
        """
        Simple broadcaster
        :return: Count of messages sent
        """
        async with self._broadcast_lock:
            count = 0
            bad_ones = []

            try:
                chat_ids = self.sort_and_shuffle_chats(chat_ids)

                for chat_id in chat_ids:
                    if isinstance(message, str):
                        final_message = message
                    else:
                        final_message = await message(chat_id)
                    if await self._send_message(chat_id, final_message):
                        count += 1
                    else:
                        bad_ones.append(chat_id)
                    await asyncio.sleep(delay)  # 10 messages per second (Limit: 30 messages per second)

                await self.remove_users(bad_ones)
            finally:
                log.info(f"{count} messages successful sent (of {len(chat_ids)})")

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
