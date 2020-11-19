import os

import aioredis
from aiogram.contrib.fsm_storage.redis import RedisStorage2


class DB:
    def __init__(self, loop):
        self.loop = loop
        self.redis: aioredis.Redis = None

    async def get_redis(self) -> aioredis.Redis:
        if self.redis is not None:
            return self.redis
        host = os.environ.get('REDIS_HOST', 'localhost')
        port = os.environ.get('REDIS_PORT', 6379)
        password = os.environ.get('REDIS_PASSWORD', None)
        redis = await aioredis.create_redis(
            f'redis://{host}:{port}',
            password=password,
            loop=self.loop)
        self.redis = redis
        return redis

    async def close_redis(self):
        self.redis.close()
        await self.redis.wait_closed()

    async def get_storage(self):
        storage = RedisStorage2(prefix='tg-fsm')
        storage._redis = await self.get_redis()
        return storage
