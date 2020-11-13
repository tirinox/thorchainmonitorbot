import asyncio

import aiohttp

from services.config import Config
from services.db import DB
from services.fetch.gecko_price import fill_rune_price_from_gecko
from services.fetch.node_ip_manager import ThorNodeAddressManager
from services.fetch.pool_price import PoolPriceFetcher
from services.models.time_series import PriceTimeSeries, BUSD_SYMBOL, RUNE_SYMBOL


async def price_fill_task(cfg, db):
    async with aiohttp.ClientSession() as session:
        thor_man = ThorNodeAddressManager(session)
        ppf = PoolPriceFetcher(cfg, db, thor_man, session)

        series = PriceTimeSeries(RUNE_SYMBOL, db)

        while True:
            busd_in_rune = await ppf.get_price_in_rune(BUSD_SYMBOL)
            print(f'busd_in_rune = {busd_in_rune}')
            await series.add(price=busd_in_rune)
            await asyncio.sleep(30)


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    cfg = Config(Config.DEFAULT_LVL_UP)
    db = DB(loop)

    loop.run_until_complete(fill_rune_price_from_gecko(db))
    # loop.run_until_complete(price_fill_task(cfg, db))
