import asyncio
import logging

from services.config import Config
from services.db import DB
from services.fetch.node_ip_manager import ThorNodeAddressManager
from services.fetch.pool_price import PoolPriceFetcher, BUSD_SYMBOL, RUNE_SYMBOL
from services.models.time_series import TimeSeries, PriceTimeSeries
from services.utils import MINUTE, HOUR


async def main(cfg, db):
    ts = PriceTimeSeries(RUNE_SYMBOL, cfg, db)
    price = await ts.select_average_ago(HOUR * 4, MINUTE * 5)
    print(price)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    loop = asyncio.get_event_loop()
    cfg = Config(Config.DEFAULT_LVL_UP)
    db = DB(loop)

    asyncio.run(main(cfg, db))
