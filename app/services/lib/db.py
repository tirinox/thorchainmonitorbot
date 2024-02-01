import os
import typing
from contextlib import asynccontextmanager

from aiogram.contrib.fsm_storage.redis import RedisStorage2
from aiogram.dispatcher import FSMContext
from redis import asyncio as aioredis


class DB:
    def __init__(self, loop):
        self.loop = loop
        self.redis: typing.Optional[aioredis.Redis] = None
        self.storage: typing.Optional[RedisStorage2] = None
        self.host = os.environ.get('REDIS_HOST', 'localhost')
        self.port = os.environ.get('REDIS_PORT', 6379)
        self.db_index = os.environ.get('REDIS_DB_INDEX', 0)
        self.password = os.environ.get('REDIS_PASSWORD', None)

    async def get_redis(self) -> aioredis.Redis:
        if self.redis is not None:
            return self.redis

        self.redis = await aioredis.from_url(
            f'redis://{self.host}:{self.port}/{self.db_index}',
            password=self.password,
            encoding="utf-8",
            decode_responses=True
        )

        self.storage = RedisStorage2(prefix='fsm')
        self.storage._redis = self.redis

        return self.redis

    async def get_storage(self):
        await self.get_redis()
        return self.storage

    async def close_redis(self):
        await self.redis.close()

    @asynccontextmanager
    async def tg_context(self, user=None, chat=None):
        fsm = FSMContext(self.storage, chat, user)
        async with fsm.proxy() as p:
            yield p

    async def test_db_connection(self):
        r = await self.get_redis()
        await r.ping()
