import asyncio
import logging
from dataclasses import dataclass

import aiohttp
import random

from services.config import Config


FALLBACK_THORCHAIN_IP = '18.159.173.48'
THORCHAIN_QUEUE_URL = lambda ip: f'http://{ip if ip else FALLBACK_THORCHAIN_IP}:1317/thorchain/queue'


THORCHAIN_SEED_URL = 'https://chaosnet-seed.thorchain.info/'  # all addresses


@dataclass
class QueueInfo:
    swap: int
    outbound: int

    @classmethod
    def error(cls):
        return cls(-1, -1)

    @property
    def is_ok(self):
        return self.swap >= 0 and self.outbound >= 0


class QueueFetcher:
    SLEEP_PERIOD = 57

    def __init__(self, cfg: Config):
        self.cfg = cfg

    async def fetch_info(self) -> QueueInfo:
        async with aiohttp.ClientSession() as session:
            logging.info(f"get seed: {THORCHAIN_SEED_URL}")
            async with session.get(THORCHAIN_SEED_URL) as resp:
                resp = await resp.json()
                ip_addr = random.choice(resp) if resp else FALLBACK_THORCHAIN_IP

            queue_url = THORCHAIN_QUEUE_URL(ip_addr)
            logging.info(f"start fetching queue: {queue_url}")
            async with session.get(queue_url) as resp:
                resp = await resp.json()
                swap_queue = int(resp.get('swap', 0))
                outbound_queue = int(resp.get('outbound', 0))
                return QueueInfo(swap_queue, outbound_queue)

    async def on_got_info(self, info: QueueInfo):
        ...

    async def run(self):
        await asyncio.sleep(3)
        while True:
            try:
                new_info = await self.fetch_info()
                if new_info.is_ok:
                    await self.on_got_info(new_info)
            except Exception as e:
                logging.exception(f'QueueFetcher error: {e}')
            await asyncio.sleep(self.SLEEP_PERIOD)
