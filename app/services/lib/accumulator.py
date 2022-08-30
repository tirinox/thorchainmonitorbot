import asyncio

from services.lib.date_utils import now_ts
from services.lib.db import DB


class Accumulator:
    def __init__(self, name, db: DB, tolerance: float):
        self.name = name
        self.db = db
        self.tolerance = tolerance

    def key(self, k):
        return f'Accum:{self.name}:{k}'

    def key_from_ts(self, ts):
        k = int(ts // self.tolerance * self.tolerance)
        return self.key(k)

    async def add(self, ts, **kwargs):
        accum_key = self.key_from_ts(ts)
        for k, v in kwargs.items():
            await self.db.redis.hincrbyfloat(accum_key, k, v)

    async def add_now(self, **kwargs):
        await self.add(now_ts(), **kwargs)

    async def set(self, ts, **kwargs):
        accum_key = self.key_from_ts(ts)
        for k, v in kwargs.items():
            await self.db.redis.hset(accum_key, k, v)

    async def get(self, timestamp=None):
        timestamp = timestamp or now_ts()
        return await self.db.redis.hgetall(self.key_from_ts(timestamp))

    async def all_my_keys(self):
        return await self.db.redis.keys(self.key('*'))

    async def clear(self, before=None):
        keys = await self.all_my_keys()
        if before:
            keys = [k for k in keys if int(k.split(':')[-1]) < before]
        if keys:
            await self.db.redis.delete(*keys)
        return len(keys)

    async def get_range(self, start_ts: float, end_ts: float = None):
        if end_ts is None:
            end_ts = now_ts()
        if start_ts < 0:
            start_ts += now_ts()

        if end_ts < start_ts:
            end_ts, start_ts = start_ts, end_ts

        timestamps = []
        ts = end_ts
        while ts > start_ts:
            timestamps.append(ts)
            ts -= self.tolerance

        if not timestamps:
            return {}

        results = await asyncio.gather(*(self.get(ts) for ts in timestamps))
        return dict(zip(timestamps, results))
