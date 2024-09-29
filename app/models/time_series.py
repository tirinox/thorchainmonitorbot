import json
import logging
from typing import Tuple

from lib.date_utils import now_ts, MINUTE
from lib.db import DB

MAX_POINTS_DEFAULT = 100000
TOLERANCE_DEFAULT = 10  # sec
MS = 1000  # milliseconds in 1 second


class TimeSeries:
    def __init__(self, name: str, db: DB, max_len=MAX_POINTS_DEFAULT):
        self.db = db
        self.name = name
        self.max_len = max_len

    @property
    def stream_name(self):
        return f'ts-stream:{self.name}'

    @staticmethod
    def range_ago(ago_sec, tolerance_sec=10):
        now_sec = now_ts()
        return (
            int((now_sec - ago_sec - tolerance_sec) * MS),
            int((now_sec - ago_sec + tolerance_sec) * MS)
        )

    @staticmethod
    def range_from_ago_to_now(ago_sec, tolerance_sec=TOLERANCE_DEFAULT):
        now_sec = now_ts()
        return (
            int((now_sec - ago_sec - tolerance_sec) * MS),
            int((now_sec + tolerance_sec) * MS)
        )

    @staticmethod
    def get_ts_from_index(index: str):
        s = index.split('-')
        return int(s[0]) / 1_000

    async def get_last_points(self, period_sec, max_points=MAX_POINTS_DEFAULT, tolerance_sec=TOLERANCE_DEFAULT):
        points = await self.select(*self.range_from_ago_to_now(period_sec, tolerance_sec=tolerance_sec),
                                   count=max_points)
        return points

    async def get_best_point_ago(self, ago_sec: float,
                                 tolerance_sec=TOLERANCE_DEFAULT, tolerance_percent=None,
                                 ref_ts=None, is_json=False) -> Tuple[dict, float]:
        ref_ts = ref_ts or now_ts()
        exact_point = ref_ts - ago_sec
        if tolerance_percent is not None:
            tolerance_sec = max(tolerance_sec, ago_sec * tolerance_percent * 0.01)
        points = await self.select(*self.range_ago(ago_sec, tolerance_sec))
        best_point = None
        best_diff = 1e30
        for index, data in points:
            ts = self.get_ts_from_index(index)
            diff = abs(exact_point - ts)
            if diff < best_diff:
                best_point, best_diff = data, diff

        if best_point and is_json:
            best_point = json.loads(best_point['json'])

        return best_point, best_diff

    async def get_last_values(self, period_sec, key,
                              max_points=MAX_POINTS_DEFAULT,
                              tolerance_sec=TOLERANCE_DEFAULT,
                              with_ts=False,
                              decoder=float):
        points = await self.get_last_points(period_sec, max_points, tolerance_sec)

        def get_data(p):
            data = p[1]
            if key:
                data = data.get(key)
                if decoder:
                    data = decoder(data)

            if with_ts:
                return self.get_ts_from_index(p[0]), data
            else:
                return data

        return [get_data(p) for p in points]

    # noinspection PyTypeChecker
    async def get_last_values_json(self, period_sec,
                                   max_points=MAX_POINTS_DEFAULT,
                                   tolerance_sec=TOLERANCE_DEFAULT,
                                   with_ts=False):
        return await self.get_last_values(period_sec, 'json', max_points, tolerance_sec, with_ts, decoder=json.loads)

    async def average(self, period_sec, key, max_points=MAX_POINTS_DEFAULT, tolerance_sec=10):
        values = await self.get_last_values(period_sec, key, max_points, tolerance_sec)
        n = len(values)
        return sum(values) / n if n else None

    async def sum(self, period_sec, key, max_points=MAX_POINTS_DEFAULT, tolerance_sec=TOLERANCE_DEFAULT):
        values = await self.get_last_values(period_sec, key, max_points, tolerance_sec)
        return sum(values)

    async def add(self, message_id=b'*', **kwargs):
        r = await self.db.get_redis()
        await r.xadd(self.stream_name, kwargs, id=message_id, maxlen=self.max_len)

    async def add_as_json(self, j: dict = None, message_id=b'*'):
        await self.add(message_id, json=json.dumps(j))

    @staticmethod
    def discrete_message_id(timestamp, tolerance=TOLERANCE_DEFAULT):
        timestamp_bucket = timestamp // tolerance * tolerance
        return f'{timestamp_bucket}-0'

    async def select(self, start, end, count=100):
        r = await self.db.get_redis()
        data = await r.xrange(self.stream_name, start, end, count=count)
        return data

    async def clear(self):
        r = await self.db.get_redis()
        await r.delete(self.stream_name)

    @staticmethod
    def adjacent_difference_points(points: list):
        return [(t2, t2 - t1, p2 - p1) for (t1, p1), (t2, p2) in zip(points, points[1:])]

    @staticmethod
    def make_sparse_points(points: list, min_interval=MINUTE):
        if not points:
            return
        ts0, v0 = points[1]
        yield ts0, v0
        for ts, v in points[1:]:
            if ts - ts0 > min_interval:
                yield ts, v
                ts0 = ts

    async def trim_oldest(self, max_len=None):
        max_len = max_len or self.max_len
        if not max_len:
            return
        prev_len = await self.get_length()
        await self.db.redis.xtrim(self.stream_name, maxlen=max_len)
        curr_len = await self.get_length()
        if curr_len != prev_len:
            logging.debug(f'Stream {self.stream_name} purged {prev_len - curr_len} old points. Now: {curr_len}.')

    async def get_length(self):
        return int(await self.db.redis.xlen(self.stream_name))


class PriceTimeSeries(TimeSeries):
    def __init__(self, coin: str, db: DB, max_len=MAX_POINTS_DEFAULT):
        super().__init__(f'price-{coin}', db, max_len=max_len)

    KEY = 'price'

    async def select_average_ago(self, ago, tolerance):
        items = await self.select(*self.range_ago(ago, tolerance))
        n, accum = 0, 0
        for _, item in items:
            price = float(item[self.KEY])
            if price > 0:
                n += 1
                accum += price
        if n:
            return accum / n
        else:
            return 0

    async def get_last_values(self,
                              period_sec,
                              key=None,
                              max_points=MAX_POINTS_DEFAULT,
                              tolerance_sec=TOLERANCE_DEFAULT,
                              with_ts=False,
                              decoder=float):
        key = key or self.KEY
        return await super().get_last_values(period_sec, key, max_points, tolerance_sec, with_ts)
