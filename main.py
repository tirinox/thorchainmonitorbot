import logging

from aiogram import Bot, Dispatcher, executor
from aiogram.types import *

from services.config import Config, DB
from localization import LocalizationManager
from services.fetch.cap_notify import CapFetcherNotification

logging.basicConfig(level=logging.INFO)

cfg = Config()
db = DB()
bot = Bot(token=cfg.telegram.bot.token, parse_mode=ParseMode.HTML)
dp = Dispatcher(bot)
locman = LocalizationManager()
fetcher = CapFetcherNotification(cfg, db, bot, locman)


@dp.message_handler(commands=['start'])
async def on_start(message: Message):
    text, kb = locman.default.lang_help()
    await message.answer(text, reply_markup=kb)


@dp.message_handler(commands=['cap'])
async def send_welcome(message: Message):
    info = await db.get_old_cap()
    loc = await locman.get_from_db(message.chat.id, db)
    welcome_text = loc.welcome_message(info)
    await message.answer(welcome_text, reply_markup=ReplyKeyboardRemove(), disable_web_page_preview=True)
    await db.add_user(message.chat.id)


@dp.message_handler(commands=['price'])
async def send_price(message: Message):
    info = await db.get_old_cap()
    loc = await locman.get_from_db(message.chat.id, db)
    price_text = loc.price_message(info)
    await message.answer(price_text, reply_markup=ReplyKeyboardRemove(), disable_web_page_preview=True)


@dp.message_handler(content_types=ContentType.TEXT)
async def on_lang_set(message: Message):
    t = message.text
    if t == locman.default.BUTTON_ENG:
        lang = 'eng'
    elif t == locman.default.BUTTON_RUS:
        lang = 'rus'
    else:
        await on_start(message)
        return

    await locman.set_lang(message.chat.id, lang, db)
    await send_welcome(message)


async def fetcher_task():
    await db.get_redis()
    await fetcher.fetch_loop()


if __name__ == '__main__':
    dp.loop.create_task(fetcher_task())
    executor.start_polling(dp, skip_updates=True)
