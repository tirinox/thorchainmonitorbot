import asyncio
import logging

import aiohttp

from localization import LocalizationManager
from services.jobs.fetch.pool_price import PoolPriceFetcher
from services.lib.config import Config
from services.lib.constants import NetworkIdents, BTC_SYMBOL, BNB_BTCB_SYMBOL
from services.lib.db import DB
from services.lib.depcont import DepContainer
import datetime


async def main(d: DepContainer):
    async with aiohttp.ClientSession() as d.session:
        await d.db.get_redis()

        day2ago = datetime.datetime.now() - datetime.timedelta(days=2)

        cfg: Config = d.cfg

        cfg.network_id = NetworkIdents.TESTNET_MULTICHAIN
        ppf = PoolPriceFetcher(d)
        result = await ppf.get_usd_per_rune_asset_per_rune_by_day(BTC_SYMBOL, day2ago.timestamp())
        print(f'Test net MC: {result} ')

        cfg.network_id = NetworkIdents.CHAOSNET_BEP2CHAIN
        ppf = PoolPriceFetcher(d)
        result = await ppf.get_usd_per_rune_asset_per_rune_by_day(BNB_BTCB_SYMBOL, day2ago.timestamp())
        print(f'Test net BEP2 Chaosnet: {result}')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    d = DepContainer()
    d.loop = asyncio.get_event_loop()
    d.cfg = Config()
    d.loc_man = LocalizationManager(d.cfg)
    d.db = DB(d.loop)

    d.loop.run_until_complete(main(d))
