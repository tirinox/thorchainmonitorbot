import asyncio
import typing
from datetime import datetime

from aioredis import Redis

from services.lib.date_utils import now_ts, DAY


class ActiveUserCounter:
    def __init__(self, r: Redis, name):
        self.r = r
        self.name = name

    def _key(self, pf):
        return f'AUC:{self.name}:{pf}'

    async def hit(self, *, user: str = '', users: typing.Iterable = None, now=None):
        users = users or (user,)
        if users or user:
            now = now or now_ts()
            key = self._key(self.key_postfix(now))
            await self.r.pfadd(key, *users)

    async def get_count(self, key_postfixes):
        keys = map(self._key, key_postfixes)
        keys = tuple(keys)
        return await self.r.pfcount(*keys)

    def key_postfix(self, now: float):
        return str(now)

    async def expire(self, postfix, time):
        await self.r.expire(self._key(postfix), time)

    async def clear(self):
        keys = await self.r.keys(self._key('*'))
        if keys:
            await self.r.delete(*keys)


class UserStats(typing.NamedTuple):
    dau: int = 0
    dau_yesterday: int = 0
    wau: int = 0
    mau: int = 0


class DailyActiveUserCounter(ActiveUserCounter):
    def key_postfix(self, now: float):
        dt = datetime.fromtimestamp(now)
        return dt.strftime("%Y-%m-%d")

    async def get_dau(self, ts: float = 0.0):
        ts = ts or now_ts()
        kpf = self.key_postfix(ts)
        return await self.get_count((kpf,))

    async def get_dau_yesterday(self):
        yesterday = now_ts() - DAY + 1.0
        return await self.get_dau(yesterday)

    async def get_au_over_days(self, days):
        assert 0 < days <= 31
        now = now_ts()
        timestamps = [now - day_ago * DAY for day_ago in range(days)]
        postfixes = map(self.key_postfix, timestamps)
        return await self.get_count(postfixes)

    async def get_wau(self):
        return await self.get_au_over_days(7)

    async def get_mau(self):
        return await self.get_au_over_days(30)

    async def get_stats(self) -> UserStats:
        dau, dau_yesterday, wau, mau = await asyncio.gather(
            self.get_dau(),
            self.get_dau_yesterday(),
            self.get_wau(),
            self.get_mau()
        )
        return UserStats(
            dau, dau_yesterday, wau, mau
        )


class ManualUserCounter:
    def __init__(self):
        self.logs = []

    async def hit(self, user, now=None):
        now = now or now_ts()
        self.logs.append((user, now))

    async def get_au_over_days(self, days):
        deadline = now_ts() - days * DAY
        filtered = (user for user, ts in self.logs if ts >= deadline)
        return len(set(filtered))

    async def get_dau_yesterday(self):
        return await self.get_au_over_days(1)

    async def get_mau(self):
        return await self.get_au_over_days(30)

    async def get_wau(self):
        return await self.get_au_over_days(7)
