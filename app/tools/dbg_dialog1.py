import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.types import ParseMode

from localization import LocalizationManager
from services.dialog.main_menu import BaseDialog
from services.lib.config import Config
from services.lib.db import DB


async def amain(cfg, db, loop):
    bot = Bot(token=cfg.telegram.bot.token, parse_mode=ParseMode.HTML)
    dp = Dispatcher(bot, loop=loop)
    loc_man = LocalizationManager()

    BaseDialog.register(cfg, db, dp, loc_man)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    loop = asyncio.get_event_loop()
    cfg = Config(Config.DEFAULT_LVL_UP)
    db = DB(loop)
    asyncio.run(amain(cfg, db, loop))
