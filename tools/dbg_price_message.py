import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.types import ParseMode

from localization import LocalizationManager, BaseLocalization
from services.lib.config import Config
from services.lib.db import DB
from services.fetch.fair_price import fetch_fair_rune_price
from services.models.price import PriceReport, LastPriceHolder
from services.notify.broadcast import Broadcaster


async def send_to_channel_test_message(cfg, db):
    loc_man = LocalizationManager()
    broadcaster = Broadcaster(cfg, bot, db)

    user_lang_map = broadcaster.telegram_chats_from_config(loc_man)

    fp = await fetch_fair_rune_price(LastPriceHolder())

    async def message_gen(chat_id):
        loc: BaseLocalization = user_lang_map[chat_id]
        return loc.price_change(PriceReport(1.601, 0.576, 0.05,
                                            fair_price=fp))

    await broadcaster.broadcast(user_lang_map.keys(), message_gen)


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
