import asyncio
import logging
from copy import deepcopy

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.types import ParseMode

from localization import LocalizationManager
from services.fetch.node_ip_manager import ThorNodeAddressManager
from services.fetch.pool_price import PoolPriceFetcher
from services.lib.config import Config
from services.lib.db import DB
from services.lib.depcont import DepContainer
from services.models.pool_info import PoolInfo
from services.models.price import LastPriceHolder
from services.notify.broadcast import Broadcaster
from services.notify.types.pool_churn import PoolChurnNotifier


async def send_to_channel_test_message(d: DepContainer):
    d.broadcaster = Broadcaster(d)

    async with aiohttp.ClientSession() as d.session:
        d.thor_man = ThorNodeAddressManager(d.cfg.thornode.seed, d.session)
        lph = LastPriceHolder()
        ppf = PoolPriceFetcher(d)
        notifier_pool_churn = PoolChurnNotifier(d)

        await ppf.get_current_pool_data_full()

        # feed original pools
        await notifier_pool_churn.on_data(ppf, None)

        lph.pool_info_map = deepcopy(lph.pool_info_map)  # make a copy
        del lph.pool_info_map['BNB.AERGO-46B']  # deleted pool
        del lph.pool_info_map['BNB.BEAR-14C']  # deleted pool
        lph.pool_info_map['BNB.FSN-E14'].status = PoolInfo.ENABLED
        lph.pool_info_map['BNB.RAVEN-F66'].status = PoolInfo.BOOTSTRAP

        lph.pool_info_map['BTC.BTC'] = PoolInfo('BTC.BTC', 18555, 100, 18555 * 100, PoolInfo.BOOTSTRAP)

        await notifier_pool_churn.on_data(ppf, None)  # must notify about changes above ^^^
        await notifier_pool_churn.on_data(ppf, None)  # no update at this momemnt!


async def main(d):
    await send_to_channel_test_message(d)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    d = DepContainer()
    d.loop = asyncio.get_event_loop()
    d.cfg = Config(Config.DEFAULT_LVL_UP)
    d.db = DB(d.loop)

    bot = Bot(token=d.cfg.telegram.bot.token, parse_mode=ParseMode.HTML)
    dp = Dispatcher(bot, loop=d.loop)
    loc_man = LocalizationManager()

    asyncio.run(main(d))
