import asyncio

import aiohttp

from services.fetch.node_ip_manager import ThorNodeAddressManager
from services.lib.config import Config
from services.lib.db import DB
from services.models.tx import StakePoolStats


async def median_test(cfg, db):
    async with aiohttp.ClientSession() as session:
        thor_man = ThorNodeAddressManager(session)

        sps = await StakePoolStats.get_from_db('TEST.TEST', db)
        sps.update(5, max_n=10)
        await sps.save(db)
        print(sps.key)
        print(f'median = {sps.median_rune_amount}')
        print(await db.redis.get(sps.key))


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    cfg = Config(Config.DEFAULT_LVL_UP)
    db = DB(loop)

    loop.run_until_complete(median_test(cfg, db))
