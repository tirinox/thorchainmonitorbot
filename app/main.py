import asyncio
import logging
import os

import aiohttp
from aiogram import Bot, Dispatcher, executor
from aiogram.types import *

from localization import LocalizationManager
from services.dialog import init_dialogs
from services.fetch.cap import CapInfoFetcher
from services.fetch.gecko_price import fill_rune_price_from_gecko
from services.fetch.node_ip_manager import ThorNodeAddressManager
from services.fetch.pool_price import PoolPriceFetcher
from services.fetch.queue import QueueFetcher
from services.fetch.tx import StakeTxFetcher
from services.lib.config import Config
from services.lib.db import DB
from services.lib.depcont import DepContainer
from services.models.price import LastPriceHolder
from services.notify.broadcast import Broadcaster
from services.notify.types.cap_notify import CapFetcherNotifier
from services.notify.types.pool_churn import PoolChurnNotifier
from services.notify.types.price_notify import PriceNotifier
from services.notify.types.queue_notify import QueueNotifier
from services.notify.types.tx_notify import StakeTxNotifier


class App:
    def __init__(self):
        d = self.deps = DepContainer()
        d.cfg = Config()

        log_level = d.cfg.get('log_level', logging.INFO)
        logging.basicConfig(
            level=logging.getLevelName(log_level),
            format='%(asctime)s.%(msecs)03d %(levelname)s %(module)s - %(funcName)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
        )

        logging.info(f"Log level: {log_level}")

        d.loop = asyncio.get_event_loop()
        d.db = DB(d.loop)
        d.bot = Bot(token=d.cfg.telegram.bot.token, parse_mode=ParseMode.HTML)
        d.dp = Dispatcher(d.bot, loop=d.loop)
        d.loc_man = LocalizationManager()
        d.broadcaster = Broadcaster(d)
        d.price_holder = LastPriceHolder()
        d.thor_man = ThorNodeAddressManager()

        init_dialogs(d)

    async def _run_tasks(self):
        d = self.deps
        d.dp.storage = await d.db.get_storage()

        if 'REPLACE_RUNE_TIMESERIES_WITH_GECKOS' in os.environ:
            await fill_rune_price_from_gecko(d.db)

        async with aiohttp.ClientSession() as d.session:
            d.thor_man.session = d.session
            await d.thor_man.reload_nodes_ip()

            self.ppf = PoolPriceFetcher(d)
            await self.ppf.get_current_pool_data_full()

            fetcher_cap = CapInfoFetcher(d, ppf=self.ppf)
            fetcher_tx = StakeTxFetcher(d)
            fetcher_queue = QueueFetcher(d)

            notifier_cap = CapFetcherNotifier(d)
            notifier_tx = StakeTxNotifier(d)
            notifier_queue = QueueNotifier(d)
            notifier_price = PriceNotifier(d)
            notifier_pool_churn = PoolChurnNotifier(d)

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
        self.deps.dp.loop.create_task(self._run_tasks())
        executor.start_polling(self.deps.dp, skip_updates=True)


if __name__ == '__main__':
    print('-' * 100)
    App().run()
