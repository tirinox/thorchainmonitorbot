import asyncio
import logging

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.types import ParseMode

from localization import LocalizationManager
from services.fetch.node_ip_manager import ThorNodeAddressManager
from services.fetch.thor_node import ThorNode
from services.lib.config import Config
from services.lib.db import DB
from services.lib.depcont import DepContainer
from services.notify.broadcast import Broadcaster


async def send_to_channel_test_message(d: DepContainer):
    d.broadcaster = Broadcaster(d)

    async with aiohttp.ClientSession() as d.session:
        d.thor_man = ThorNodeAddressManager(d.session)
        d.thor_nodes = ThorNode(d.thor_man, d.session, cohort_size=3, consensus=2)

        r = await d.thor_nodes.request('/thorchain/queue')
        print(r)


async def main(d):
    await send_to_channel_test_message(d)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    d = DepContainer()
    d.loop = asyncio.get_event_loop()
    d.cfg = Config()
    d.db = DB(d.loop)

    bot = Bot(token=d.cfg.telegram.bot.token, parse_mode=ParseMode.HTML)
    dp = Dispatcher(bot, loop=d.loop)
    loc_man = LocalizationManager()

    asyncio.run(main(d))
