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
from services.models.pool_info import PoolInfo
from services.models.price import LastPriceHolder
from services.lib.money import short_asset_name
from services.notify.broadcast import Broadcaster
from services.notify.types.pool_churn import PoolChurnNotifier


async def send_to_channel_test_message(cfg, db):
    loc_man = LocalizationManager()
    broadcaster = Broadcaster(cfg, bot, db)
    thor_man = ThorNodeAddressManager.shared()
    async with aiohttp.ClientSession() as session:
        thor_man.session = session
        lph = LastPriceHolder()
        ppf = PoolPriceFetcher(cfg, db, thor_man, session, lph)
        notifier_pool_churn = PoolChurnNotifier(cfg, db, broadcaster, loc_man)

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


async def main(cfg, db):
    await send_to_channel_test_message(cfg, db)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    loop = asyncio.get_event_loop()
    cfg = Config(Config.DEFAULT_LVL_UP)
    db = DB(loop)

    bot = Bot(token=cfg.telegram.bot.token, parse_mode=ParseMode.HTML)
    dp = Dispatcher(bot, loop=loop)
    loc_man = LocalizationManager()

    asyncio.run(main(cfg, db))
