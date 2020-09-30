import asyncio
import logging

import aiohttp

from services.config import Config
from services.models.model import StakeTx


class StakeTxFetcher:
    SLEEP_PERIOD = 60

    def __init__(self, cfg: Config):
        self.cfg = cfg

    def form_tx_url(self, offset=0, limit=10):
        base_url = self.cfg.thorchain.chaosnet.urls.txs
        return base_url.format(offset=offset, limit=limit)

    def parse_tx(self, j):
        txs = j['txs']
        for tx in txs:
            if tx['status'] == 'Success':
                yield StakeTx.load_from_midgard(tx)

    async def fetch_tx(self):
        async with aiohttp.ClientSession() as session:
            try:
                url = self.form_tx_url(0, 10)
                logging.info(f"start fetching tx: {url}")
                async with session.get(url) as resp:
                    json = await resp.json()
                    txs = self.parse_tx(json)
                    return list(txs)
            except (ValueError, TypeError, IndexError, ZeroDivisionError, KeyError) as e:
                print(e)
                return []

    async def on_got_txs(self, txs):
        ...

    async def run(self):
        await asyncio.sleep(3)
        while True:
            r = await self.fetch_tx()
            print(*r)
            await asyncio.sleep(self.SLEEP_PERIOD)
