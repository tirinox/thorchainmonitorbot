import asyncio
import logging
from random import random

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.types import ParseMode

from localization import LocalizationManager
from services.cooldown import CooldownTracker
from services.fetch.price import get_prices_of, STABLE_COIN, get_price_of, get_pool_info, BNB_BNB, fair_rune_price
from services.fetch.queue import QueueFetcher
from services.notify.broadcast import Broadcaster
from services.config import Config, DB
from services.fetch.tx import StakeTxFetcher
from services.models.tx import StakePoolStats
from services.notify.types.tx_notify import StakeTxNotifier
from services.utils import a_result_cached

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


async def foo1():
    await db.get_redis()
    users = await broadcaster.all_users()
    print(broadcaster.sort_and_shuffle_chats(users))

    print(broadcaster.sort_and_shuffle_chats([
        10, -1, 20, 50, -200, "@test", -300, -250, 11, 12, 14, "@maxism"
    ]))
    # await StakeTxFetcher.fetch_loop()


loop = asyncio.get_event_loop()
lock = asyncio.Lock()

async def mock_broadcaster(tag, n, delay=0.2):
    async with lock:
        for i in range(n):
            print(f'mock_broadcaster : {tag} step {i}')
            await asyncio.sleep(delay)


async def foo2():
    await asyncio.gather(mock_broadcaster('first', 10, 0.2), mock_broadcaster('second', 12, 0.1))


async def foo3():
    f = StakeTxFetcher(cfg, db)
    await f.run()


async def foo4():
    await db.get_redis()
    pool = 'BNB.BNB'
    bnb_st = await StakePoolStats.get_from_db(pool, db)

    print(f"bnb_st = {bnb_st}")

    def stake(amt):
        bnb_st.update(amt)
        print(f"bnb_st = {bnb_st}")

    for _ in range(30):
        stake(100)

    stake(100000)

    for _ in range(50):
        stake(100)

    await bnb_st.save(db)

    await asyncio.sleep(1)


async def foo5():
    async with aiohttp.ClientSession() as session:
        mp = await get_prices_of(session, [STABLE_COIN, BNB_BNB])
        print(mp)
        print(await get_price_of(session, STABLE_COIN))


async def foo6():
    await StakePoolStats.clear_all_data(db)

    fetcher_tx = StakeTxNotifier(cfg, db, broadcaster, loc_man)
    await fetcher_tx.run()


async def foo7():
    async with aiohttp.ClientSession() as session:
        j = await get_pool_info(session, [STABLE_COIN, BNB_BNB])
        print(*j.values(), sep='\n\n')


async def foo8():
    async with aiohttp.ClientSession() as session:
        fp = await fair_rune_price(session)
        print(fp)


@a_result_cached(5)
async def test_rand():
    return random()


async def foo9():
    print(await test_rand())
    print(await test_rand())
    await asyncio.sleep(3)
    print(await test_rand())
    print('same above?')
    await asyncio.sleep(3)
    print('must be different:')
    print(await test_rand())


async def foo10():
    tr = CooldownTracker(db)
    print((await tr.can_do('1', 10)))
    await tr.do('1')
    print((await tr.can_do('1', 3)))
    await asyncio.sleep(3.5)
    print((await tr.can_do('1', 3)))
    print((await tr.can_do('1', 10)))


async def foo11():
    qf = QueueFetcher(cfg)
    r = await qf.fetch_info()
    print(r)


async def start_foos():
    await db.get_redis()
    await foo11()


if __name__ == '__main__':
    loop.run_until_complete(start_foos())
