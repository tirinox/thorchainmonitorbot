import json
import time

from services.lib.db import DB


class TimeSeries:
    def __init__(self, name: str, db: DB):
        self.db = db
        self.name = name

    @property
    def stream_name(self):
        return f'ts-stream:{self.name}'

    @staticmethod
    def range_ago(ago_sec, tolerance_sec=10):
        now_sec = time.time()
        return (
            int((now_sec - ago_sec - tolerance_sec) * 1000),
            int((now_sec - ago_sec + tolerance_sec) * 1000)
        )

    @staticmethod
    def range_from_ago_to_now(ago_sec, tolerance_sec=10):
        now_sec = time.time()
        return (
            int((now_sec - ago_sec - tolerance_sec) * 1000),
            int((now_sec - tolerance_sec) * 1000)
        )

    @staticmethod
    def get_ts_from_index(index: bytes):
        s = index.decode().split('-')
        return int(s[0]) / 1_000

    async def get_last_points(self, period_sec, max_points=10000, tolerance_sec=10):
        points = await self.select(*self.range_from_ago_to_now(period_sec, tolerance_sec=tolerance_sec),
                                   count=max_points)
        return points

    async def get_last_values(self, period_sec, key, max_points=10000, tolerance_sec=10, with_ts=False,
                              decoder=float):
        points = await self.get_last_points(period_sec, max_points, tolerance_sec)
        if isinstance(key, str):
            key = key.encode('utf-8')

        if with_ts:
            values = [(self.get_ts_from_index(p[0]), decoder(p[1][key])) for p in points if key in p[1]]
        else:
            values = [decoder(p[1][key]) for p in points if key in p[1]]

        return values

    # noinspection PyTypeChecker
    async def get_last_values_json(self, period_sec, max_points=10000, tolerance_sec=10, with_ts=False):
        return await self.get_last_values(period_sec, 'json', max_points, tolerance_sec, with_ts, decoder=json.loads)

    async def average(self, period_sec, key, max_points=10000, tolerance_sec=10):
        values = await self.get_last_values(period_sec, key, max_points, tolerance_sec)
        n = len(values)
        return sum(values) / n if n else None

    async def sum(self, period_sec, key, max_points=10000, tolerance_sec=10):
        values = await self.get_last_values(period_sec, key, max_points, tolerance_sec)
        return sum(values)

    async def add(self, message_id=b'*', **kwargs):
        r = await self.db.get_redis()
        await r.xadd(self.stream_name, kwargs, message_id=message_id)

    async def add_as_json(self, message_id=b'*', j: dict = None):
        await self.add(message_id, json=json.dumps(j))

    async def select(self, start, end, count=100):
        r = await self.db.get_redis()
        data = await r.xrange(self.stream_name, start, end, count=count)
        return data

    async def clear(self):
        r = await self.db.get_redis()
        await r.delete(key=self.stream_name)


class PriceTimeSeries(TimeSeries):
    def __init__(self, coin: str, db: DB):
        super().__init__(f'price-{coin}', db)

    KEY = b'price'

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

    async def get_last_values(self, period_sec, key, max_points=10000, tolerance_sec=10, with_ts=False,
                              decoder=float):
        key = key or self.KEY
        return await super().get_last_values(period_sec, key, max_points, tolerance_sec, with_ts)
