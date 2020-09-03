import logging
import asyncio

from fetcher import InfoFetcher
from broadcast import broadcaster
from config import Config, DB

from aiogram import Bot, Dispatcher, executor, types

logging.basicConfig(level=logging.INFO)

cfg = Config()
db = DB()

bot = Bot(token=cfg.telegram.bot.token, parse_mode=types.ParseMode.HTML)
dp = Dispatcher(bot)


@dp.message_handler(commands=['start', 'help'])
async def send_welcome(message: types.Message):
    cap, stk = await fetcher.get_old_cap()
    await message.reply(f"Hi! <b>{stk:.0f}</b> of <b>{cap:.0f}</b> is staked now.")
    my_id = message.from_user.id
    await db.add_user(my_id)


@dp.message_handler()
async def echo(message: types.Message):
    await message.reply("Not supported")


async def on_changed_cap(old_max_cap, max_cap, staked):
    users = await db.all_users()
    verb = "lifted" if old_max_cap < max_cap else "dropped"
    message = f'<b>Cap {verb} from {old_max_cap:.0f} up to {max_cap:.0f}!</b>\n' \
              f'Come on!\n' \
              f'https://chaosnet.bepswap.com/stake/BNB'
    _, _, bad_ones = await broadcaster(bot, users, message)
    await db.remove_users(bad_ones)


if __name__ == '__main__':
    fetcher = InfoFetcher(cfg, db, on_changed_cap)
    dp.loop.create_task(fetcher.fetch_loop())
    executor.start_polling(dp, skip_updates=True)
