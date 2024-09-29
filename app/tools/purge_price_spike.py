import asyncio
import logging

from lib.constants import RUNE_SYMBOL_POOL, RUNE_SYMBOL_DET
from lib.date_utils import DAY
from models.time_series import PriceTimeSeries
from tools.lib.lp_common import LpAppFramework


async def purge_spike_time_series(series: PriceTimeSeries, interval, max_value):
    # points = await series.select(*series.range_ago(interval), count=1000000)
    points = await series.get_last_points(interval, 1_000_000)
    message_ids = [p[0] for p in points if float(p[1]['price']) > max_value]
    print(f'Bad points for {series.stream_name} are {len(message_ids)} of total {len(points)}')

    r = series.db.redis
    if message_ids:
        await r.xdel(series.stream_name, *message_ids)


INTERVAL = 5 * DAY
POOL_PRICE_THRESHOLD = 11.0
DET_PRICE_THRESHOLD = 2.0


async def main():
    lp_app = LpAppFramework(log_level=logging.INFO)
    async with lp_app:
        await lp_app.prepare(brief=True)

        pool_price_series = PriceTimeSeries(RUNE_SYMBOL_POOL, lp_app.deps.db)
        await purge_spike_time_series(pool_price_series, INTERVAL, POOL_PRICE_THRESHOLD)

        deterministic_price_series = PriceTimeSeries(RUNE_SYMBOL_DET, lp_app.deps.db)
        await purge_spike_time_series(deterministic_price_series, INTERVAL, DET_PRICE_THRESHOLD)


if __name__ == '__main__':
    asyncio.run(main())
