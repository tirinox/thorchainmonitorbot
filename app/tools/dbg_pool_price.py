import asyncio
import logging

import aiohttp
from aiothornode.connector import ThorConnector

from localization import LocalizationManager
from main import get_thor_env_by_network_id
from services.jobs.fetch.pool_price import PoolPriceFetcher
from services.lib.config import Config
from services.lib.constants import NetworkIdents, BTC_SYMBOL, BNB_BTCB_SYMBOL
from services.lib.db import DB
from services.lib.depcont import DepContainer
import datetime


async def test_prices_at_day_mctn(d: DepContainer, day2ago):
    cfg: Config = d.cfg

    cfg.network_id = NetworkIdents.TESTNET_MULTICHAIN
    ppf = PoolPriceFetcher(d)
    usd_per_rune, usd_per_asset = await ppf.get_usd_price_of_rune_and_asset_by_day(BTC_SYMBOL, day2ago)
    print(f'Test net MC: {usd_per_rune=}, ({BTC_SYMBOL}) {usd_per_asset=} ')


async def test_prices_at_day_sccn(d: DepContainer, day2ago):
    cfg: Config = d.cfg
    cfg.network_id = NetworkIdents.CHAOSNET_BEP2CHAIN
    ppf = PoolPriceFetcher(d)
    usd_per_rune, usd_per_asset = await ppf.get_usd_price_of_rune_and_asset_by_day(BNB_BTCB_SYMBOL, day2ago,
                                                                                   caching=False)
    print(f'Test net BEP2 Chaosnet: {usd_per_rune=}, ({BNB_BTCB_SYMBOL}) {usd_per_asset=}')


async def test_prices_at_day(d: DepContainer):
    day2ago = datetime.date(2021, 4, 11)

    await test_prices_at_day_sccn(d, day2ago)


async def test_thor_pools_caching_mctn(d: DepContainer):
    d.cfg.network_id = NetworkIdents.TESTNET_MULTICHAIN

    d.thor_connector = ThorConnector(get_thor_env_by_network_id(d.cfg.network_id), d.session)
    ppf = PoolPriceFetcher(d)
    pp = await ppf.get_current_pool_data_full(caching=True, height=501)
    print(pp)


async def test_thor_pools_caching_sccn(d: DepContainer):
    d.cfg.network_id = NetworkIdents.CHAOSNET_BEP2CHAIN

    d.thor_connector = ThorConnector(get_thor_env_by_network_id(d.cfg.network_id), d.session)
    ppf = PoolPriceFetcher(d)
    pp = await ppf.get_current_pool_data_full(caching=True, height=200101)
    print(pp)


async def test_thor_pools_caching(d: DepContainer):
    await test_thor_pools_caching_sccn(d)


async def test_pool_cache(d):
    d.cfg.network_id = NetworkIdents.TESTNET_MULTICHAIN
    ppf = PoolPriceFetcher(d)
    day2ago = datetime.date(2021, 3, 31)

    pool_info = await ppf.get_pool_info_by_day(BTC_SYMBOL, day2ago, caching=True)
    print(pool_info)


async def main(d: DepContainer):
    async with aiohttp.ClientSession() as d.session:
        await d.db.get_redis()

        # await test_prices(d)
        # await test_pool_cache(d)
        await test_prices_at_day(d)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    d = DepContainer()
    d.loop = asyncio.get_event_loop()
    d.cfg = Config()
    d.loc_man = LocalizationManager(d.cfg)
    d.db = DB(d.loop)

    d.loop.run_until_complete(main(d))
