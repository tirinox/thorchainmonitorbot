import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.types import *

from services.broadcast import Broadcaster
from services.config import Config, DB
from services.fetch.tx import StakeTxFetcher

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


if __name__ == '__main__':
    loop.run_until_complete(foo2())
