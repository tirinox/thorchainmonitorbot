import asyncio
import logging

import aiohttp

from services.config import Config
from services.fetch.model import MIDGARD_MULT


class StakeTxFetcher:
    SLEEP_PERIOD = 60

    def __init__(self, cfg: Config):
        self.cfg = cfg

    def form_tx_url(self, offset=0, limit=10):
        base_url = self.cfg.thorchain.chaosnet.urls.txs
        return base_url.format(offset=offset, limit=limit)

    async def fetch_tx(self):
        async with aiohttp.ClientSession() as session:
            try:
                url = self.form_tx_url(0, 10)
                logging.info(f"start fetching tx: {url}")
                async with session.get(url) as resp:
                    json = await resp.json()
                    print(json)


            except (ValueError, TypeError, IndexError, ZeroDivisionError, KeyError):
                return
            else:
                return

    async def on_got_info(self):
        ...

    async def run(self):
        await asyncio.sleep(3)
        while True:
            await self.fetch_tx()
            await asyncio.sleep(self.SLEEP_PERIOD)
