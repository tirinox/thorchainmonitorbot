import asyncio

import aiohttp

from services.fetch.pool_price import PoolPriceFetcher
from services.lib.config import Config
from services.lib.db import DB
from services.lib.depcont import DepContainer
from services.models.time_series import PriceTimeSeries, BUSD_SYMBOL, RUNE_SYMBOL


async def price_fill_task(d: DepContainer):
    async with aiohttp.ClientSession() as d.session:
        ppf = PoolPriceFetcher(d)

        series = PriceTimeSeries(RUNE_SYMBOL, d.db)

        while True:
            busd_in_rune = await ppf.get_price_in_rune(BUSD_SYMBOL)
            print(f'busd_in_rune = {busd_in_rune}')
            await series.add(price=busd_in_rune)
            await asyncio.sleep(30)


if __name__ == '__main__':
    d = DepContainer()
    d.loop = asyncio.get_event_loop()
    d.cfg = Config(Config.DEFAULT_LVL_UP)
    d.db = DB(d.loop)

    d.loop.run_until_complete(price_fill_task(d))
