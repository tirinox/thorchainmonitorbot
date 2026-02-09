from datetime import datetime

from lib.date_utils import now_ts, DAY
from lib.db import DB
from lib.utils import take_closest, gather_in_batches


class Accumulator:
    """
    This class is used to count the sum of events that occur within a certain time interval.
    Items are put into buckets with tolerance.
    """

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

    async def get(self, timestamp=None, conv_to_float=True):
        timestamp = timestamp or now_ts()
        r = await self.db.redis.hgetall(self.key_from_ts(timestamp))
        return self._convert_values_to_float(r) if conv_to_float else r

    async def sum(self, start_ts: float, end_ts: float = None, key=None):
        points = await self.get_range(start_ts, end_ts, conv_to_float=True)
        s = 0.0
        for d in points.values():
            s += d.get(key, 0.0)
        return s

    async def average(self, start_ts: float, end_ts: float = None, key=None):
        points = await self.get_range(start_ts, end_ts, conv_to_float=True)
        s = 0.0
        n = 0
        for d in points.values():
            s += d.get(key, 0.0)
            n += 1
        return s / n if n > 0 else 0.0

    @staticmethod
    def _prepare_ts(start_ts: float, end_ts: float = None):
        if end_ts is None:
            end_ts = now_ts()
        if start_ts < 0:
            start_ts += now_ts()

        if end_ts < start_ts:
            end_ts, start_ts = start_ts, end_ts

        return start_ts, end_ts

    async def get_range(self, start_ts: float, end_ts: float = None, conv_to_float=True):
        start_ts, end_ts = self._prepare_ts(start_ts, end_ts)

        timestamps = []
        ts = end_ts
        while ts > start_ts:
            timestamps.append(ts)
            ts -= self.tolerance

        if not timestamps:
            return {}

        results = await gather_in_batches([self.get(ts, conv_to_float) for ts in timestamps], 10)
        return dict(zip(timestamps, results))

    async def get_range_n(self, start_ts: float, end_ts: float = None, conv_to_float=True, n=10):
        assert n >= 2

        start_ts, end_ts = self._prepare_ts(start_ts, end_ts)

        points = await self.get_range(start_ts, end_ts, conv_to_float)
        real_time_points = list(sorted(points.keys()))
        dt = (end_ts - start_ts) / (n - 1)

        results = []

        for step in range(n):
            ts = start_ts + dt * step
            closest_ts = take_closest(real_time_points, ts, ignore_outliers=True)
            # print(ts, closest_ts, (ts - closest_ts) if closest_ts else '???')
            item = points[closest_ts] if closest_ts else {}
            results.append((ts, item))

        return results

    @staticmethod
    def _convert_values_to_float(r: dict):
        return {k: float(v) for k, v in r.items()}

    async def all_my_keys(self):
        return await self.db.redis.keys(self.key('*'))

    async def clear(self, before=None, dry_run=False):
        keys = await self.all_my_keys()
        if before:
            keys = [k for k in keys if int(k.split(':')[-1]) < before]
        if keys:
            if dry_run:
                timestamps = [int(k.split(':')[-1]) for k in keys]
                min_ts, max_ts = min(timestamps), max(timestamps)
                print(f'Would delete {len(keys)}: '
                      f'from {datetime.fromtimestamp(min_ts)} to {datetime.fromtimestamp(max_ts)}')
            else:
                await self.db.redis.delete(*keys)
        return len(keys)


class DailyAccumulator(Accumulator):
    def __init__(self, name, db: DB):
        super().__init__(name, db, DAY)

    def key_from_ts(self, ts):
        dt = datetime.fromtimestamp(ts)
        return self.key(dt.strftime("%Y-%m-%d"))
