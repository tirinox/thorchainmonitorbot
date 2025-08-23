import json
import time
from collections.abc import Callable
from functools import wraps
from typing import Union

from web3.datastructures import AttributeDict

from lib.db import DB


class Web3TxEncoder(json.JSONEncoder):
    def default(self, z):
        if isinstance(z, bytes):
            return z.hex()
        elif isinstance(z, AttributeDict):
            return dict(z)
        else:
            return super().default(z)


class Cache:
    def __init__(self, db: DB, name):
        self.db = db
        self.name = name

    def load_transform(self, data):
        return json.loads(data) if data else None

    def save_transform(self, data):
        if isinstance(data, AttributeDict):
            data = dict(data)
        if not isinstance(data, str):
            data = json.dumps(data, cls=Web3TxEncoder)
        return data

    async def load(self, key):
        data = await self.db.redis.hget(self.name, key)
        return self.load_transform(data)

    async def store(self, key, data):
        if key:
            data = self.save_transform(data)
            await self.db.redis.hset(self.name, key, data)

    async def clear(self):
        await self.db.redis.delete(self.name)


class CacheNamedTuple(Cache):
    def __init__(self, db: DB, name, tuple_class: type):
        self.tuple_class = tuple_class
        super().__init__(db, name)

    def load_transform(self, data):
        data = super(CacheNamedTuple, self).load_transform(data)
        try:
            # noinspection PyArgumentList
            data = self.tuple_class(**data)
        except TypeError:
            # apparently the format has changed, so reload and save it again
            data = None
        return data

    def save_transform(self, data):
        # noinspection PyProtectedMember
        return super(CacheNamedTuple, self).save_transform(data._asdict())


def async_cache_ignore_arguments(ttl=60):
    def decorator(func):
        last_update_ts = -1.0
        last_result = None

        @wraps(func)
        async def wrapper(*args, **kwargs):
            nonlocal last_result, last_update_ts
            if last_result is None or last_update_ts < 0 or time.monotonic() - ttl > last_update_ts:
                last_result = await func(*args, **kwargs)
                last_update_ts = time.monotonic()
            return last_result

        return wrapper

    return decorator


def _freeze(obj):
    """Best-effort, hashable snapshot for common Python types."""
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    if isinstance(obj, (tuple, list)):
        return tuple(_freeze(x) for x in obj)
    if isinstance(obj, set):
        return "__set__", tuple(sorted(_freeze(x) for x in obj))
    if isinstance(obj, dict):
        return tuple(sorted((k, _freeze(v)) for k, v in obj.items()))
    # Fallback: repr (may be unstable across runs for some objects)
    return "__repr__", repr(obj)


def _make_key(args, kwargs):
    return _freeze(args), _freeze(kwargs)


def async_cache(ttl: Union[Callable, int, float] = 60):
    def decorator(func):
        cache = {}
        _ttl = ttl

        @wraps(func)
        async def wrapper(*args, **kwargs):
            key = _make_key(args, kwargs)
            now = time.monotonic()
            eff_ttl = _ttl(*args, **kwargs) if callable(_ttl) else _ttl
            if key not in cache or now - cache[key][1] > eff_ttl:
                result = await func(*args, **kwargs)
                cache[key] = (result, now)
            return cache[key][0]

        # Runtime TTL control
        def set_cache_ttl(new_ttl):
            nonlocal _ttl
            _ttl = new_ttl

        wrapper.set_cache_ttl = set_cache_ttl
        return wrapper

    return decorator
