from aiogram.utils.exceptions import MessageCantBeDeleted, MessageToEditNotFound, MessageToDeleteNotFound

from comm.telegram.telegram import TelegramBot
from lib.db import DB
from lib.logs import WithLogger


class MessageCategoryDB(WithLogger):
    def __init__(self, db: DB, user_id: int, category: str):
        super().__init__()
        self.db = db
        self.user_id = user_id
        self.category = category

    @property
    def db_key(self):
        return f'Message:Tracker:{self.user_id}:{self.category}'

    async def push(self, *message_ids):
        for message_id in message_ids:
            if not message_id:
                self.logger.error(f'U: {self.user_id} Empty message_id for category {self.category}')
                continue

            key = self.db_key
            await self.db.redis.sadd(key, message_id)

    async def pop(self):
        key = self.db_key
        return await self.db.redis.spop(key)

    async def get_all(self):
        key = self.db_key
        return await self.db.redis.smembers(key)

    async def clear(self):
        key = self.db_key
        await self.db.redis.delete(key)

    async def pop_delete(self, bot: TelegramBot):
        message_id = await self.pop()
        if message_id:
            try:
                self.logger.info(f'U: {self.user_id} Deleting message {message_id}')
                await bot.bot.delete_message(self.user_id, message_id)
            except (MessageCantBeDeleted, MessageToEditNotFound, MessageToDeleteNotFound) as e:
                self.logger.error(f'can not delete message {e!r}')
        return message_id

    async def delete_all(self, bot: TelegramBot):
        message_id = await self.pop_delete(bot)
        while message_id:
            message_id = await self.pop_delete(bot)
