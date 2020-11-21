import os
import typing
from contextlib import asynccontextmanager

import aioredis
from aiogram.contrib.fsm_storage.redis import RedisStorage2
from aiogram.dispatcher import FSMContext


class DB:
    def __init__(self, loop):
        self.loop = loop
        self.redis: typing.Optional[aioredis.Redis] = None
        self.storage: typing.Optional[RedisStorage2] = None
        self.host = os.environ.get('REDIS_HOST', 'localhost')
        self.port = os.environ.get('REDIS_PORT', 6379)
        self.password = os.environ.get('REDIS_PASSWORD', None)

    async def get_redis(self) -> aioredis.Redis:
        if self.redis is not None:
            return self.redis

        self.redis = await aioredis.create_redis(
            f'redis://{self.host}:{self.port}',
            password=self.password,
            loop=self.loop)

        self.storage = RedisStorage2(prefix='fsm')
        self.storage._redis = await self.get_redis()

        return self.redis

    async def get_storage(self):
        await self.get_redis()
        return self.storage

    async def close_redis(self):
        self.redis.close()
        await self.redis.wait_closed()

    @asynccontextmanager
    async def tg_context(self, user=None, chat=None):
        fsm = FSMContext(self.storage, chat, user)
        async with fsm.proxy() as p:
            yield p
