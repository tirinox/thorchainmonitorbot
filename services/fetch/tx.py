import asyncio
import logging

import aiohttp

from services.config import Config
from services.fetch.model import MIDGARD_MULT


class StakeTxFetcher:
    SLEEP_PERIOD = 60

    def __init__(self, cfg: Config):
        self.cfg = cfg

    async def fetch_tx(self):
        urls = self.cfg.thorchain.chaosnet.urls

        async with aiohttp.ClientSession() as session:
            try:
                logging.info("start fetching")


            except (ValueError, TypeError, IndexError, ZeroDivisionError, KeyError):
                return
            else:
                return

    async def on_got_info(self):
        ...

    async def fetch_loop(self):
        await asyncio.sleep(3)
        while True:
            await self.fetch_tx()
            await asyncio.sleep(self.SLEEP_PERIOD)
