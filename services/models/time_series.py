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
        now_ms = int(time.time() * 1000)
        t_ms = int(tolerance_sec * 1000)
        return now_ms - ago_sec - t_ms, now_ms - ago_sec + t_ms

    async def add(self, message_id=b'*', **kwargs):
        r = await self.db.get_redis()
        await r.xadd(self.stream_name, kwargs, message_id=message_id)

    async def select(self, start, end):
        r = await self.db.get_redis()
        data = await r.xrange(self.stream_name, start, end)
        return data


class PriceTimeSeries(TimeSeries):
    def __init__(self, coin: str, cfg: Config, db: DB):
        super().__init__(f'price-{coin}', cfg, db)
