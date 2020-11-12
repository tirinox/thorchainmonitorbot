import asyncio
import logging

from services.config import Config
from services.db import DB
from services.fetch.node_ip_manager import ThorNodeAddressManager
from services.fetch.pool_price import PoolPriceFetcher
from services.models.time_series import TimeSeries


async def main(cfg, db):
    t = TimeSeries('test2', cfg, db)
    # await t.add(value=10)

    r = await t.select(*t.range(120, 1200))
    print(r)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    loop = asyncio.get_event_loop()
    cfg = Config(Config.DEFAULT_LVL_UP)
    db = DB(loop)

    asyncio.run(main(cfg, db))
