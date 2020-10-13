import asyncio
import logging

import aiohttp
from aiogram import Bot, Dispatcher, executor
from aiogram.types import *
from aiogram.dispatcher import filters

from services.fetch.price import fair_rune_price
from services.models.cap_info import ThorInfo
from services.notify.broadcast import Broadcaster
from services.config import Config, DB
from localization import LocalizationManager
from services.notify.types.cap_notify import CapFetcherNotification
from services.notify.types.tx_notify import StakeTxNotifier

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
fetcher_cap = CapFetcherNotification(cfg, broadcaster, loc_man)
fetcher_tx = StakeTxNotifier(cfg, db, broadcaster, loc_man)


@dp.message_handler(commands=['start'])
async def on_start(message: Message):
    text, kb = loc_man.default.lang_help()
    await message.answer(text, reply_markup=kb,
                         disable_notification=True)


@dp.message_handler(commands=['cap'])
async def send_welcome(message: Message):
    info = await ThorInfo.get_old_cap(db)
    loc = await loc_man.get_from_db(message.chat.id, db)
    welcome_text = loc.welcome_message(info)
    await message.answer(welcome_text, reply_markup=ReplyKeyboardRemove(),
                         disable_web_page_preview=True,
                         disable_notification=True)
    await broadcaster.register_user(message.chat.id)


@dp.message_handler(commands=['price'])
async def send_price(message: Message):
    info = await ThorInfo.get_old_cap(db)
    loc = await loc_man.get_from_db(message.chat.id, db)
    async with aiohttp.ClientSession() as session:
        fp = await fair_rune_price(session)
    price_text = loc.price_message(info, fp)
    await message.answer(price_text, reply_markup=ReplyKeyboardRemove(),
                         disable_web_page_preview=True,
                         disable_notification=True)


@dp.message_handler(commands=['help'])
async def send_price(message: Message):
    loc = await loc_man.get_from_db(message.chat.id, db)
    await message.answer(loc.help(), reply_markup=ReplyKeyboardRemove(),
                         disable_web_page_preview=True,
                         disable_notification=True)


@dp.message_handler(filters.RegexpCommandsFilter(regexp_commands=[r'/.*']))
async def on_unknown_command(message: Message):
    loc = await loc_man.get_from_db(message.chat.id, db)
    await message.answer(loc.unknown_command(), disable_notification=True)


@dp.message_handler(content_types=ContentType.TEXT)
async def on_lang_set(message: Message):
    t = message.text
    if t == loc_man.default.BUTTON_ENG:
        lang = 'eng'
    elif t == loc_man.default.BUTTON_RUS:
        lang = 'rus'
    else:
        await on_start(message)
        return

    await loc_man.set_lang(message.chat.id, lang, db)
    await send_welcome(message)


async def fetcher_task():
    await db.get_redis()

    await asyncio.gather(
        fetcher_cap.run(),
        fetcher_tx.run()
    )


if __name__ == '__main__':
    dp.loop.create_task(fetcher_task())
    executor.start_polling(dp, skip_updates=True)
