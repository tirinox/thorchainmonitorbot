import json

from lib.cooldown import Cooldown
from lib.date_utils import now_ts
from lib.db import DB


class RateLimiter:
    def __init__(self, db: DB, key, limit: int, period: float):
        self.db = db
        self.key = key
        self.limit = limit
        self.period = period

    async def is_limited(self):
        return await self.is_limited_s(self.db, self.key, self.limit, self.period)

    async def clear(self):
        return await self.clear_s(self.db, self.key)

    @staticmethod
    def _full_key(k):
        return f'RateLimit:{k}'

    @classmethod
    async def is_limited_s(cls, db: DB, key: str, limit: int, period: float):
        if not key:
            return True

        if limit <= 0 or period <= 0:
            return False

        key = cls._full_key(key)

        r = db.redis
        sec, micro_sec = (await r.time())
        t = sec + micro_sec * 1e-6
        separation = period / limit
        await r.setnx(key, 0.0)
        tat = max(float(await r.get(key)), t)
        if tat - t <= period - separation:
            new_tat = max(tat, t) + separation
            await r.set(key, new_tat)
            return False
        return True

    @classmethod
    async def clear_s(cls, db: DB, key: str):
        await db.redis.delete(cls._full_key(key))


class RateLimitCooldown(RateLimiter):
    ON_COOLDOWN = 'on_cd'
    HIT_LIMIT = 'hit_limit'
    GOOD = 'good'

    def __init__(self, db: DB, key, limit: int, period: float, cd_sec: float):
        super().__init__(db, key, limit, period)
        self.cd = Cooldown(db, f'RateLimitCooldown:{key}', cd_sec)

    async def hit(self):
        if not await self.cd.can_do():
            return self.ON_COOLDOWN
        else:
            good = not await self.is_limited()
            if good:
                return self.GOOD
            else:
                await self.cd.do()
                return self.HIT_LIMIT


class SlidingWindowLimiter:
    """
    Strict cap: at most `limit` hits within any rolling `period` seconds.
    Unlike RateLimiter (GCRA), it never lets a burst be followed by more hits inside the same window.
    Meant for low limits: hit timestamps are stored as a JSON list.
    """

    def __init__(self, db: DB, key: str, limit: int, period: float):
        self.db = db
        self.key = key
        self.limit = limit
        self.period = period

    @property
    def is_disabled(self):
        return self.limit <= 0 or self.period <= 0

    @property
    def _full_key(self):
        return f'SlidingWindow:{self.key}'

    async def get_hits(self, now=None) -> list:
        now = now or now_ts()
        raw = await self.db.redis.get(self._full_key)
        try:
            hits = [float(t) for t in json.loads(raw)]
        except (TypeError, ValueError):
            return []
        return sorted(t for t in hits if t > now - self.period)

    async def hit(self, now=None) -> bool:
        """Registers a hit and returns True, or returns False if the limit is already reached."""
        if self.is_disabled:
            return True
        now = now or now_ts()
        hits = await self.get_hits(now)
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        await self.db.redis.set(self._full_key, json.dumps(hits), ex=int(self.period) + 1)
        return True

    async def free_at(self, now=None) -> float:
        """Timestamp when the next hit will be allowed (now, if it is allowed already)."""
        now = now or now_ts()
        if self.is_disabled:
            return now
        hits = await self.get_hits(now)
        if len(hits) < self.limit:
            return now
        return hits[-self.limit] + self.period

    async def clear(self):
        await self.db.redis.delete(self._full_key)
