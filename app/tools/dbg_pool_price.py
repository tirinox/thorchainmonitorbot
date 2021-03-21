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

        day2ago = datetime.date(2021, 3, 20)

        cfg: Config = d.cfg

        cfg.network_id = NetworkIdents.TESTNET_MULTICHAIN
        ppf = PoolPriceFetcher(d)
        usd_per_rune, usd_per_asset = await ppf.get_usd_price_of_rune_and_asset_by_day(BTC_SYMBOL, day2ago)
        print(f'Test net MC: {usd_per_rune=}, ({BTC_SYMBOL}) {usd_per_asset=} ')

        cfg.network_id = NetworkIdents.CHAOSNET_BEP2CHAIN
        ppf = PoolPriceFetcher(d)
        usd_per_rune, usd_per_asset = await ppf.get_usd_price_of_rune_and_asset_by_day(BNB_BTCB_SYMBOL, day2ago, caching=False)
        print(f'Test net BEP2 Chaosnet: {usd_per_rune=}, ({BNB_BTCB_SYMBOL}) {usd_per_asset=}')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    d = DepContainer()
    d.loop = asyncio.get_event_loop()
    d.cfg = Config()
    d.loc_man = LocalizationManager(d.cfg)
    d.db = DB(d.loop)

    d.loop.run_until_complete(main(d))
