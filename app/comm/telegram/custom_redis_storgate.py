import asyncio
import json
import typing
from abc import ABC, abstractmethod

from aiogram.dispatcher.storage import BaseStorage
from redis.asyncio import Redis

STATE_KEY = 'state'
STATE_DATA_KEY = 'data'
STATE_BUCKET_KEY = 'bucket'


class AioRedisAdapterBase(ABC):
    """Base aioredis adapter class."""

    def __init__(
            self,
            host: str = "localhost",
            port: int = 6379,
            db: typing.Optional[int] = None,
            password: typing.Optional[str] = None,
            ssl: typing.Optional[bool] = None,
            pool_size: int = 10,
            loop: typing.Optional[asyncio.AbstractEventLoop] = None,
            prefix: str = "fsm",
            state_ttl: typing.Optional[int] = None,
            data_ttl: typing.Optional[int] = None,
            bucket_ttl: typing.Optional[int] = None,
            **kwargs,
    ):
        self._host = host
        self._port = port
        self._db = db
        self._password = password
        self._ssl = ssl
        self._pool_size = pool_size
        self._loop = loop or asyncio.get_event_loop()
        self._kwargs = kwargs
        self._prefix = (prefix,)

        self._state_ttl = state_ttl
        self._data_ttl = data_ttl
        self._bucket_ttl = bucket_ttl

        self._redis: typing.Optional["Redis"] = None
        self._connection_lock = asyncio.Lock()

    @abstractmethod
    async def get_redis(self) -> Redis:
        """Get Redis connection."""
        pass

    async def close(self):
        """Grace shutdown."""
        pass

    async def wait_closed(self):
        """Wait for grace shutdown finishes."""
        pass

    async def set(self, name, value, ex=None, **kwargs):
        """Set the value at key ``name`` to ``value``."""
        if ex == 0:
            ex = None
        return await self._redis.set(name, value, ex=ex, **kwargs)

    async def get(self, name, **kwargs):
        """Return the value at key ``name`` or None."""
        return await self._redis.get(name)

    async def delete(self, *names):
        """Delete one or more keys specified by ``names``"""
        return await self._redis.delete(*names)

    async def keys(self, pattern, **kwargs):
        """Returns a list of keys matching ``pattern``."""
        return await self._redis.keys(pattern, **kwargs)

    async def flushdb(self):
        """Delete all keys in the current database."""
        return await self._redis.flushdb()


class AioRedisAdapterV2(AioRedisAdapterBase):
    """Redis adapter for aioredis v2."""

    async def get_redis(self) -> Redis:
        """Get Redis connection."""
        async with self._connection_lock:  # to prevent race
            if self._redis is None:
                self._redis = Redis(
                    host=self._host,
                    port=self._port,
                    db=self._db,
                    password=self._password,
                    ssl=self._ssl,
                    max_connections=self._pool_size,
                    decode_responses=True,
                    **self._kwargs,
                )
        return self._redis


class RedisStorage3(BaseStorage):
    """
    Busted Redis-base storage for FSM.
    Works with Redis connection pool and customizable keys prefix.

    Usage:

    .. code-block:: python3

        storage = RedisStorage2('localhost', 6379, db=5, pool_size=10, prefix='my_fsm_key')
        dp = Dispatcher(bot, storage=storage)

    And need to close Redis connection when shutdown

    .. code-block:: python3

        await dp.storage.close()
        await dp.storage.wait_closed()

    """

    def __init__(
            self,
            loop: typing.Optional[asyncio.AbstractEventLoop] = None,
            prefix: str = "fsm",
            state_ttl: typing.Optional[int] = None,
            data_ttl: typing.Optional[int] = None,
            bucket_ttl: typing.Optional[int] = None,
            redis: typing.Optional[Redis] = None,
            **kwargs,
    ):
        self._loop = loop or asyncio.get_event_loop()
        self._kwargs = kwargs
        self._prefix = (prefix,)

        self._state_ttl = state_ttl
        self._data_ttl = data_ttl
        self._bucket_ttl = bucket_ttl

        self._redis: typing.Optional[AioRedisAdapterBase] = redis
        self._connection_lock = asyncio.Lock()

    async def _get_adapter(self) -> AioRedisAdapterBase:
        """Get adapter based on aioredis version."""
        if self._redis is None:
            raise RuntimeError(f"Redis connection is not initialized. ")
        return self._redis

    def generate_key(self, *parts):
        return ':'.join(self._prefix + tuple(map(str, parts)))

    async def close(self):
        if self._redis:
            return await self._redis.close()

    async def wait_closed(self):
        if self._redis and hasattr(self._redis, 'wait_closed'):
            await self._redis.wait_closed()
        self._redis = None

    async def get_state(self, *, chat: typing.Union[str, int, None] = None, user: typing.Union[str, int, None] = None,
                        default: typing.Optional[str] = None) -> typing.Optional[str]:
        chat, user = self.check_address(chat=chat, user=user)
        key = self.generate_key(chat, user, STATE_KEY)
        redis = await self._get_adapter()
        return await redis.get(key) or self.resolve_state(default)

    async def get_data(self, *, chat: typing.Union[str, int, None] = None, user: typing.Union[str, int, None] = None,
                       default: typing.Optional[dict] = None) -> typing.Dict:
        chat, user = self.check_address(chat=chat, user=user)
        key = self.generate_key(chat, user, STATE_DATA_KEY)
        redis = await self._get_adapter()
        raw_result = await redis.get(key)
        if raw_result:
            return json.loads(raw_result)
        return default or {}

    async def set_state(self, *, chat: typing.Union[str, int, None] = None, user: typing.Union[str, int, None] = None,
                        state: typing.Optional[typing.AnyStr] = None):
        chat, user = self.check_address(chat=chat, user=user)
        key = self.generate_key(chat, user, STATE_KEY)
        redis = await self._get_adapter()
        if state is None:
            await redis.delete(key)
        else:
            await redis.set(key, self.resolve_state(state), ex=self._state_ttl)

    async def set_data(self, *, chat: typing.Union[str, int, None] = None, user: typing.Union[str, int, None] = None,
                       data: typing.Dict = None):
        chat, user = self.check_address(chat=chat, user=user)
        key = self.generate_key(chat, user, STATE_DATA_KEY)
        redis = await self._get_adapter()
        if data:
            await redis.set(key, json.dumps(data), ex=self._data_ttl)
        else:
            await redis.delete(key)

    async def update_data(self, *, chat: typing.Union[str, int, None] = None, user: typing.Union[str, int, None] = None,
                          data: typing.Dict = None, **kwargs):
        if data is None:
            data = {}
        temp_data = await self.get_data(chat=chat, user=user, default={})
        temp_data.update(data, **kwargs)
        await self.set_data(chat=chat, user=user, data=temp_data)

    def has_bucket(self):
        return True

    async def get_bucket(self, *, chat: typing.Union[str, int, None] = None, user: typing.Union[str, int, None] = None,
                         default: typing.Optional[dict] = None) -> typing.Dict:
        chat, user = self.check_address(chat=chat, user=user)
        key = self.generate_key(chat, user, STATE_BUCKET_KEY)
        redis = await self._get_adapter()
        raw_result = await redis.get(key)
        if raw_result:
            return json.loads(raw_result)
        return default or {}

    async def set_bucket(self, *, chat: typing.Union[str, int, None] = None, user: typing.Union[str, int, None] = None,
                         bucket: typing.Dict = None):
        chat, user = self.check_address(chat=chat, user=user)
        key = self.generate_key(chat, user, STATE_BUCKET_KEY)
        redis = await self._get_adapter()
        if bucket:
            await redis.set(key, json.dumps(bucket), ex=self._bucket_ttl)
        else:
            await redis.delete(key)

    async def update_bucket(self, *, chat: typing.Union[str, int, None] = None,
                            user: typing.Union[str, int, None] = None,
                            bucket: typing.Dict = None, **kwargs):
        if bucket is None:
            bucket = {}
        temp_bucket = await self.get_bucket(chat=chat, user=user)
        temp_bucket.update(bucket, **kwargs)
        await self.set_bucket(chat=chat, user=user, bucket=temp_bucket)

    async def reset_all(self, full=True):
        """
        Reset states in DB

        :param full: clean DB or clean only states
        :return:
        """
        redis = await self._get_adapter()

        if full:
            await redis.flushdb()
        else:
            keys = await redis.keys(self.generate_key('*'))
            await redis.delete(*keys)

    async def get_states_list(self) -> typing.List[typing.Tuple[str, str]]:
        """
        Get list of all stored chat's and user's

        :return: list of tuples where first element is chat id and second is user id
        """
        redis = await self._get_adapter()
        result = []

        keys = await redis.keys(self.generate_key('*', '*', STATE_KEY))
        for item in keys:
            *_, chat, user, _ = item.split(':')
            result.append((chat, user))

        return result
