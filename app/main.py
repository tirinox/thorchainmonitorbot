import asyncio
import logging
import os

import aiohttp
from aiogram import Bot, Dispatcher, executor
from aiogram.types import *

from localization import LocalizationManager
from services.dialog.main_menu import MainMenuDialog
from services.dialog.stake_info import StakeDialog
from services.fetch.cap import CapInfoFetcher
from services.fetch.gecko_price import fill_rune_price_from_gecko
from services.fetch.node_ip_manager import ThorNodeAddressManager
from services.fetch.pool_price import PoolPriceFetcher
from services.fetch.queue import QueueFetcher
from services.fetch.tx import StakeTxFetcher
from services.lib.config import Config
from services.lib.db import DB
from services.models.price import LastPriceHolder
from services.notify.broadcast import Broadcaster
from services.notify.types.cap_notify import CapFetcherNotifier
from services.notify.types.pool_churn import PoolChurnNotifier
from services.notify.types.price_notify import PriceNotifier
from services.notify.types.queue_notify import QueueNotifier
from services.notify.types.tx_notify import StakeTxNotifier


class App:
    def __init__(self):
        print('-' * 100)

        cfg = self.cfg = Config()

        log_level = self.cfg.get('log_level', logging.INFO)
        logging.basicConfig(
            level=logging.getLevelName(log_level),
            format='%(asctime)s.%(msecs)03d %(levelname)s %(module)s - %(funcName)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
        )

        logging.info(f"Log level: {log_level}")

        self.loop = asyncio.get_event_loop()
        db = self.db = DB(self.loop)
        self.bot = Bot(token=self.cfg.telegram.bot.token, parse_mode=ParseMode.HTML)
        dp = self.dp = Dispatcher(self.bot, loop=self.loop)
        loc_man = self.loc_man = LocalizationManager()
        broadcaster = self.broadcaster = Broadcaster(self.cfg, self.bot, self.db)
        price_holder = self.price_holder = LastPriceHolder()

        self.thor_man = ThorNodeAddressManager.shared()

        MainMenuDialog.register(cfg, db, dp, loc_man,
                                broadcaster=broadcaster,
                                price_holder=price_holder)
        StakeDialog.register(cfg, db, dp, loc_man,
                             broadcaster=broadcaster,
                             price_holder=price_holder)

    async def _run_tasks(self):
        self.dp.storage = await self.db.get_storage()

        if 'REPLACE_RUNE_TIMESERIES_WITH_GECKOS' in os.environ:
            await fill_rune_price_from_gecko(self.db)

        async with aiohttp.ClientSession() as session:
            cfg, db, loc_man, thor_man = self.cfg, self.db, self.loc_man, self.thor_man
            price_holder, broadcaster = self.price_holder, self.broadcaster

            thor_man.session = session
            await thor_man.reload_nodes_ip()

            self.ppf = PoolPriceFetcher(cfg, db, thor_man, session, holder=price_holder)
            fetcher_cap = CapInfoFetcher(cfg, db, session, ppf=self.ppf)
            fetcher_tx = StakeTxFetcher(cfg, db, session, price_holder=price_holder)
            fetcher_queue = QueueFetcher(cfg, db, session, thor_man=thor_man)

            notifier_cap = CapFetcherNotifier(cfg, db, broadcaster, loc_man)
            notifier_tx = StakeTxNotifier(cfg, db, broadcaster, loc_man)
            notifier_queue = QueueNotifier(cfg, db, broadcaster, loc_man)
            notifier_price = PriceNotifier(cfg, db, broadcaster, loc_man)
            notifier_pool_churn = PoolChurnNotifier(cfg, db, broadcaster, loc_man)

            fetcher_cap.subscribe(notifier_cap)
            fetcher_tx.subscribe(notifier_tx)
            fetcher_queue.subscribe(notifier_queue)
            self.ppf.subscribe(notifier_price)
            self.ppf.subscribe(notifier_pool_churn)

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
