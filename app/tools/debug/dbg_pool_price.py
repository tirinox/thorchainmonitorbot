import asyncio
import datetime
import logging

import aiohttp
from aiothornode.connector import ThorConnector

from localization.manager import LocalizationManager
from services.jobs.fetch.pool_price import PoolFetcher, PoolInfoFetcherMidgard
from services.lib.config import Config
from services.lib.constants import NetworkIdents, BTC_SYMBOL
from services.lib.db import DB
from services.lib.depcont import DepContainer
from tools.lib.lp_common import LpAppFramework


def set_network(d: DepContainer, network_id: str):
    d.cfg.network_id = network_id
    d.thor_connector = ThorConnector(d.cfg.get_thor_env_by_network_id(), d.session)


async def demo_thor_pools_caching_mctn(d: DepContainer):
    set_network(d, NetworkIdents.TESTNET_MULTICHAIN)

    ppf = PoolFetcher(d)
    pp = await ppf.load_pools(caching=True, height=501)
    print(pp)


async def demo_price_continuously(d: DepContainer):
    ppf = PoolFetcher(d)
    d.thor_connector = ThorConnector(d.cfg.get_thor_env_by_network_id(), d.session)
    while True:
        await ppf.fetch()
        await asyncio.sleep(2.0)


async def demo_get_pool_info_midgard(d: DepContainer):
    ppf = PoolInfoFetcherMidgard(d, 10)
    pool_map = await ppf.fetch()
    print(pool_map)


async def demo_cache_blocks(app: LpAppFramework):
    await app.deps.last_block_fetcher.run_once()
    last_block = app.deps.last_block_store.last_thor_block
    print(last_block)

    pf: PoolFetcher = app.deps.pool_fetcher
    pools = await pf.load_pools(7_000_000, caching=True)
    print(pools)

    pools = await pf.load_pools(8_200_134, caching=True)
    print(pools)

    pools = await pf.load_pools(8_200_136, caching=True)
    print(pools)


async def main():
    app = LpAppFramework()
    async with app(brief=True):
        await demo_cache_blocks(app)


if __name__ == '__main__':
    asyncio.run(main())
