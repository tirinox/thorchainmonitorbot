import asyncio
import logging
import os

import aiohttp
from aiogram import Bot, Dispatcher, executor
from aiogram.types import *

from localization import LocalizationManager
from services.config import Config
from services.db import DB
from services.dialog.dialog import register_commands
from services.fetch.cap import CapInfoFetcher
from services.fetch.gecko_price import fill_rune_price_from_gecko
from services.fetch.node_ip_manager import ThorNodeAddressManager
from services.fetch.pool_price import PoolPriceFetcher
from services.fetch.queue import QueueFetcher
from services.fetch.tx import StakeTxFetcher
from services.models.price import LastPrice
from services.notify.broadcast import Broadcaster
from services.notify.types.cap_notify import CapFetcherNotification
from services.notify.types.price_notify import PriceNotifier
from services.notify.types.queue_notify import QueueNotifier
from services.notify.types.tx_notify import StakeTxNotifier


class App:
    def __init__(self):
        self.cfg = Config()

        log_level = self.cfg.get('log_level', logging.INFO)
        logging.basicConfig(level=logging.getLevelName(log_level))
        logging.info(f"Log level: {log_level}")

        self.loop = asyncio.get_event_loop()
        self.db = DB(self.loop)
        self.bot = Bot(token=self.cfg.telegram.bot.token, parse_mode=ParseMode.HTML)
        self.dp = Dispatcher(self.bot, loop=self.loop)
        self.loc_man = LocalizationManager()
        self.broadcaster = Broadcaster(self.bot, self.db)
        self.price_holder = LastPrice()

        self.thor_man = ThorNodeAddressManager.shared()

        register_commands(self.cfg, self.dp, self.loc_man, self.db, self.broadcaster, self.price_holder)

    async def _run_tasks(self):
        await self.db.get_redis()
        self.dp.storage = await self.db.get_storage()

        if 'REPLACE_RUNE_TIMESERIES_WITH_GECKOS' in os.environ:
            await fill_rune_price_from_gecko(self.db)

        async with aiohttp.ClientSession() as session:
            self.thor_man.session = session
            await self.thor_man.reload_nodes_ip()

            notifier_cap = CapFetcherNotification(self.cfg, self.db, self.broadcaster, self.loc_man)
            notifier_tx = StakeTxNotifier(self.cfg, self.db, self.broadcaster, self.loc_man, None)
            notifier_queue = QueueNotifier(self.cfg, self.db, self.broadcaster, self.loc_man)
            notifier_price = PriceNotifier(self.cfg, self.db, self.broadcaster, self.loc_man)

            self.ppf = PoolPriceFetcher(self.cfg, self.db, self.thor_man, session, delegate=notifier_price,
                                        holder=self.price_holder)
            fetcher_cap = CapInfoFetcher(self.cfg, self.db, session, ppf=self.ppf, delegate=notifier_cap)
            fetcher_tx = StakeTxFetcher(self.cfg, self.db, session, delegate=notifier_tx, ppf=self.ppf)
            fetcher_queue = QueueFetcher(self.cfg, self.db, session, thor_man=self.thor_man, delegate=notifier_queue)

            notifier_tx.fetcher = fetcher_tx  # fixme: back link

            await asyncio.gather(*(task.run() for task in [
                self.ppf,
                fetcher_tx,
                fetcher_cap,
                fetcher_queue,
            ]))

    def run(self):
        self.dp.loop.create_task(self._run_tasks())
        executor.start_polling(self.dp, skip_updates=True)


if __name__ == '__main__':
    App().run()
