import asyncio
import logging

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.types import ParseMode

from localization import LocalizationManager
from services.lib.config import Config
from services.lib.db import DB
from services.fetch.node_ip_manager import ThorNodeAddressManager
from services.fetch.pool_price import PoolPriceFetcher
from services.models.tx import StakePoolStats
from services.notify.broadcast import Broadcaster
from services.lib.utils import progressbar

cfg = Config()

log_level = cfg.get('log_level', logging.INFO)

logging.basicConfig(level=logging.getLevelName(log_level))
logging.info(f"Log level: {log_level}")

loop = asyncio.get_event_loop()
db = DB(loop)

bot = Bot(token=cfg.telegram.bot.token, parse_mode=ParseMode.HTML)
dp = Dispatcher(bot, loop=loop)
loc_man = LocalizationManager()
broadcaster = Broadcaster(bot, db)

loop = asyncio.get_event_loop()
lock = asyncio.Lock()


async def mock_broadcaster(tag, n, delay=0.2):
    async with lock:
        for i in range(n):
            print(f'mock_broadcaster : {tag} step {i}')
            await asyncio.sleep(delay)


async def foo2():
    await asyncio.gather(mock_broadcaster('first', 10, 0.2), mock_broadcaster('second', 12, 0.1))


async def foo12():
    print(progressbar(0, 100, 30))
    print(progressbar(-14, 100, 30))
    print(progressbar(10, 100, 30))
    print(progressbar(1200, 100, 30))
    await StakePoolStats.clear_all_data(db)


async def foo13():
    async with aiohttp.ClientSession() as session:
        thor_man = ThorNodeAddressManager(session)
        ppf = PoolPriceFetcher(cfg, db, session=session, thor_man=thor_man)
        data = await ppf.get_current_pool_data_full()
    print(data)


async def start_foos():
    await db.get_redis()
    await foo13()


if __name__ == '__main__':
    loop.run_until_complete(start_foos())
