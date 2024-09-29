import asyncio

from redis.asyncio import Redis

from lib.db import DB


class OneToOne:
    def __init__(self, db: DB, prefix: str):
        self.db = db
        self.prefix = prefix

    async def _redis(self) -> Redis:
        return await self.db.get_redis()

    def key(self, k):
        return f'121:{self.prefix}:{k}'

    async def clear(self):
        r = await self._redis()
        keys = await r.keys(self.key('*'))
        if keys:
            await r.delete(*keys)

    async def put(self, one, two, safe=True):
        r = self.db.redis
        if safe:
            await self.delete(one)
        await asyncio.gather(
            r.set(self.key(one), two),
            r.set(self.key(two), one)
        )

    async def get(self, k):
        return await self.db.redis.get(self.key(k))

    async def delete(self, name):
        partner = await self.get(name)
        items = (partner, name) if partner else (name,)
        await self.db.redis.delete(*map(self.key, items))
