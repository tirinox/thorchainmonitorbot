import asyncio
import logging

import aiohttp

from services.fetch.price import get_prices_of, STABLE_COIN, get_price_of
from services.notify.broadcast import Broadcaster
from services.config import Config, DB
from services.fetch.tx import StakeTxFetcher
from services.models.tx import StakeTx, StakePoolStats
from services.notify.tx_notify import StakeTxNotifier

logging.basicConfig(level=logging.INFO)

cfg = Config()
loop = asyncio.get_event_loop()
db = DB(loop)

bk = Broadcaster(None, db)


async def foo1():
    await db.get_redis()
    users = await bk.all_users()
    print(bk.sort_and_shuffle_chats(users))

    print(bk.sort_and_shuffle_chats([
        10, -1, 20, 50, -200, -300, -250, 11, 12, 14
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
        mp = await get_prices_of(session, [STABLE_COIN, 'BNB.BNB'])
        print(mp)
        print(await get_price_of(session, STABLE_COIN))


async def foo6():
    await StakePoolStats.clear_all_data(db)
    # return

    fetcher_tx = StakeTxNotifier(cfg, db, None, None)
    await fetcher_tx.run()


async def start_foos():
    await db.get_redis()
    await foo6()


if __name__ == '__main__':
    loop.run_until_complete(start_foos())
