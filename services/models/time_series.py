import time

from services.config import Config
from services.db import DB


class TimeSeries:
    def __init__(self, name: str, cfg: Config, db: DB):
        self.db = db
        self.cfg = cfg
        self.name = name

    @property
    def stream_name(self):
        return f'ts-stream:{self.name}'

    @staticmethod
    def range(ago_sec, tolerance_sec):
        now_sec = int(time.time())
        t_sec = int(tolerance_sec)
        return (now_sec - ago_sec - t_sec) * 1000, (now_sec - ago_sec + t_sec) * 1000

    async def add(self, message_id=b'*', **kwargs):
        r = await self.db.get_redis()
        await r.xadd(self.stream_name, kwargs, message_id=message_id)

    async def select(self, start, end, count=100):
        r = await self.db.get_redis()
        data = await r.xrange(self.stream_name, start, end, count=count)
        return data


class PriceTimeSeries(TimeSeries):
    def __init__(self, coin: str, cfg: Config, db: DB):
        super().__init__(f'price-{coin}', cfg, db)

    async def select_average_ago(self, ago, tolerance):
        items = await self.select(*self.range(ago, tolerance))
        n, accum = 0, 0
        for _, item in items:
            price = float(item[b'price'])
            if price > 0:
                n += 1
                accum += price
        if n:
            return accum / n
        else:
            return 0


