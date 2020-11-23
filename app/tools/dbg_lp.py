import asyncio

import aiohttp

from services.fetch.lp_calc import LiqPoolFetcher
from services.lib.config import Config
from services.lib.db import DB
from services.lib.depcont import DepContainer
from services.models.stake_info import BNB_CHAIN


async def lp_test(d: DepContainer):
    async with aiohttp.ClientSession() as d.session:
        lpf = LiqPoolFetcher(d)
        await lpf.fetch('bnb1rv89nkw2x5ksvhf6jtqwqpke4qhh7jmudpvqmj', BNB_CHAIN)



if __name__ == '__main__':
    d = DepContainer()
    d.loop = asyncio.get_event_loop()
    d.cfg = Config(Config.DEFAULT_LVL_UP)
    d.db = DB(d.loop)

    d.loop.run_until_complete(lp_test(d))
