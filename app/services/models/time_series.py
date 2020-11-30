import time

from services.lib.db import DB

BNB_SYMBOL = 'BNB.BNB'
BUSD_SYMBOL = 'BNB.BUSD-BD1'
RUNE_SYMBOL = 'BNB.RUNE-B1A'
BTCB_SYMBOL = 'BNB.BTCB-1DE'
ETHB_SYMBOL = 'BNB.ETH-1C9'
RUNE_SYMBOL_DET = 'RUNE-DET'


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
            int((now_sec - + tolerance_sec) * 1000)
        )

    async def add(self, message_id=b'*', **kwargs):
        r = await self.db.get_redis()
        await r.xadd(self.stream_name, kwargs, message_id=message_id)

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

    async def select_average_ago(self, ago, tolerance):
        items = await self.select(*self.range_ago(ago, tolerance))
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
