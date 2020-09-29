import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.types import *

from services.broadcast import sort_and_shuffle_chats
from services.config import Config, DB
from services.fetch.tx import StakeTxFetcher

logging.basicConfig(level=logging.INFO)

cfg = Config()
db = DB()
bot = Bot(token=cfg.telegram.bot.token, parse_mode=ParseMode.HTML)
dp = Dispatcher(bot)


async def foo():
    await db.get_redis()
    print(await db.all_users())

    print(sort_and_shuffle_chats([
        10, -1, 20, 50, -200, -300, -250, 11, 12, 14
    ]))
    # await StakeTxFetcher.fetch_loop()


if __name__ == '__main__':
    asyncio.run(foo())
