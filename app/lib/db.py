import os
import socket
import typing
from contextlib import asynccontextmanager

from aiogram.dispatcher import FSMContext
from redis import asyncio as aioredis

from comm.telegram.custom_redis_storgate import RedisStorage3
from lib.logs import WithLogger


class _RedisBackedDB(WithLogger):
    ENV_PREFIX = 'REDIS'
    SERVICE_NAME = 'Redis'
    LOCALHOST_ALIASES = {'localhost', '127.0.0.1', '::1'}
    DOCKER_SERVICE_HOSTS = {'redis', 'keydb'}

    def __init__(self, env_prefix: str | None = None, service_name: str | None = None):
        super().__init__()
        self.redis: typing.Optional[aioredis.Redis] = None
        self.storage: typing.Optional[RedisStorage3] = None
        self.env_prefix = env_prefix or self.ENV_PREFIX
        self.service_name = service_name or self.SERVICE_NAME
        self.host = self._resolve_host(os.environ.get(f'{self.env_prefix}_HOST', 'localhost'))
        self.port = os.environ.get(f'{self.env_prefix}_PORT', 6379)
        self.db_index = int(os.environ.get(f'{self.env_prefix}_DB_INDEX', 0))
        if self.db_index != 0:
            self.logger.warning(f'Using non-default {self.service_name} DB index: {self.db_index}')
        self.password = os.environ.get(f'{self.env_prefix}_PASSWORD', None)

    def _resolve_host(self, host: str | None) -> str:
        host = (host or 'localhost').strip()

        if host in self.LOCALHOST_ALIASES:
            return host

        try:
            socket.getaddrinfo(host, None)
        except socket.gaierror:
            if host in self.DOCKER_SERVICE_HOSTS:
                self.logger.warning(
                    f'{self.service_name} host "{host}" not resolvable outside Docker; using localhost.'
                )
                return 'localhost'

        return host

    async def get_redis(self) -> aioredis.Redis:
        if self.redis is not None:
            return self.redis

        redis = await aioredis.from_url(
            f'redis://{self.host}:{self.port}/{self.db_index}',
            password=self.password,
            encoding="utf-8",
            decode_responses=True
        )
        self.redis = redis

        self.storage = RedisStorage3(prefix='fsm', redis=redis)
        # self.storage._redis = self.redis

        return redis

    async def get_storage(self):
        await self.get_redis()
        return self.storage

    async def close_redis(self):
        if self.redis is not None:
            await self.redis.close()

    @asynccontextmanager
    async def tg_context(self, user=None, chat=None):
        fsm = FSMContext(self.storage, chat, user)
        async with fsm.proxy() as p:
            yield p

    async def test_db_connection(self):
        r = await self.get_redis()
        await r.ping()


class DB(_RedisBackedDB):
    def __init__(self):
        super().__init__(env_prefix='REDIS', service_name='Redis')


class KeyDB(_RedisBackedDB):
    def __init__(self):
        super().__init__(env_prefix='KEYDB', service_name='KeyDB')

