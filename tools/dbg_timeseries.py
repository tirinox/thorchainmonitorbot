import asyncio
import logging

from services.config import Config
from services.db import DB
from services.fetch.node_ip_manager import ThorNodeAddressManager
from services.fetch.pool_price import PoolPriceFetcher, BUSD_SYMBOL
from services.models.time_series import TimeSeries


async def main(cfg, db):
    thor_man = ThorNodeAddressManager()
    ppf = PoolPriceFetcher(thor_man)
    r = await ppf.fetch_pool_data_historic(BUSD_SYMBOL)
    print(r)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    loop = asyncio.get_event_loop()
    cfg = Config(Config.DEFAULT_LVL_UP)
    db = DB(loop)

    asyncio.run(main(cfg, db))
