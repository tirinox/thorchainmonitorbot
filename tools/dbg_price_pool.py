import asyncio

from services.config import Config
from services.db import DB
from services.fetch.node_ip_manager import ThorNodeAddressManager
from services.fetch.pool_price import PoolPriceFetcher
from services.models.time_series import PriceTimeSeries


async def price_fill_task(cfg, db):
    thor_man = ThorNodeAddressManager()
    ppf = PoolPriceFetcher(thor_man)

    series = PriceTimeSeries('rune', cfg, db)

    while True:
        busd_in_rune = await ppf.get_price_in_rune(ppf.BUSD)
        print(f'busd_in_rune = {busd_in_rune}')
        await series.add(price=busd_in_rune)
        await asyncio.sleep(30)


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    cfg = Config(Config.DEFAULT_LVL_UP)
    db = DB(loop)

    loop.run_until_complete(price_fill_task(cfg, db))
