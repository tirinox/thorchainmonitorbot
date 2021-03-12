import asyncio
import logging

from services.lib.config import Config
from services.lib.db import DB
from services.models.time_series import PriceTimeSeries
from services.lib.constants import RUNE_SYMBOL
from services.lib.datetime import MINUTE, HOUR


async def main(cfg, db):
    ts = PriceTimeSeries(RUNE_SYMBOL, db)
    price = await ts.select_average_ago(HOUR * 4, MINUTE * 5)
    print(price)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    loop = asyncio.get_event_loop()
    cfg = Config()
    db = DB(loop)

    asyncio.run(main(cfg, db))
