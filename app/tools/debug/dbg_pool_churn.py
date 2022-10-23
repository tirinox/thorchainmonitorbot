import asyncio
import logging
from copy import deepcopy

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.types import ParseMode
from aiothornode.connector import ThorConnector

from localization.manager import LocalizationManager
from services.jobs.fetch.pool_price import PoolPriceFetcher, PoolInfoFetcherMidgard
from services.lib.config import Config
from services.lib.constants import DOGE_SYMBOL
from services.lib.db import DB
from services.lib.depcont import DepContainer
from services.models.pool_info import PoolInfo
from services.models.price import LastPriceHolder
from services.notify.broadcast import Broadcaster
from services.notify.types.pool_churn_notify import PoolChurnNotifier
from tools.lib.lp_common import LpAppFramework


async def send_to_channel_test_message(d: DepContainer):
    d.broadcaster = Broadcaster(d)

    async with aiohttp.ClientSession() as d.session:
        d.thor_connector = ThorConnector(d.cfg.get_thor_env_by_network_id(), d.session)
        d.price_holder = LastPriceHolder()
        ppf = PoolInfoFetcherMidgard(d, 100)
        notifier_pool_churn = PoolChurnNotifier(d)

        ppf_old = PoolPriceFetcher(d)
        d.price_holder.pool_info_map = await ppf_old.get_current_pool_data_full()
        await ppf.get_pool_info_midgard()

        # feed original pools
        await notifier_pool_churn.on_data(ppf, None)
        await notifier_pool_churn.on_data(ppf, d.price_holder.pool_info_map)  # must notify about changes above ^^^

        d.price_holder.pool_info_map = deepcopy(d.price_holder.pool_info_map)  # make a copy
        # del lph.pool_info_map['ETH.USDT-0XDAC17F958D2EE523A2206206994597C13D831EC7']  # deleted pool
        del d.price_holder.pool_info_map['ETH.SUSHI-0X6B3595068778DD592E39A122F4F5A5CF09C90FE2']  # deleted pool
        d.price_holder.pool_info_map['BNB.AVA-645'].status = PoolInfo.STAGED
        d.price_holder.pool_info_map['BNB.FTM-A64'].status = PoolInfo.AVAILABLE
        d.price_holder.pool_info_map[DOGE_SYMBOL] = PoolInfo(DOGE_SYMBOL, 18555, 18555, 100, PoolInfo.STAGED)

        await notifier_pool_churn.on_data(ppf, d.price_holder.pool_info_map)  # no update at this moment!


async def main():
    lp_app = LpAppFramework(log_level=logging.INFO)
    async with lp_app:
        await lp_app.prepare(brief=True)
        await send_to_channel_test_message(lp_app.deps)


if __name__ == '__main__':
    asyncio.run(main())
