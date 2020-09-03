import logging
import asyncio

from fetcher import fetch_loop
from config import Config

from aiogram import Bot, Dispatcher, executor, types

cfg = Config()

logging.basicConfig(level=logging.INFO)

# Initialize bot and dispatcher
bot = Bot(token=cfg.telegram.bot.token)
dp = Dispatcher(bot)


@dp.message_handler(commands=['start', 'help'])
async def send_welcome(message: types.Message):
    await message.reply("Hi!")


@dp.message_handler()
async def echo(message: types.Message):
    await message.reply("Not supported")


if __name__ == '__main__':
    dp.loop.create_task(fetch_loop(cfg))
    executor.start_polling(dp, skip_updates=True)
