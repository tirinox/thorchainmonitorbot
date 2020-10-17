import asyncio
import logging
from dataclasses import dataclass

import aiohttp

from services.config import Config


THORCHAIN_QUEUE_URL = 'http://18.159.173.48:1317/thorchain/queue'


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
            try:
                logging.info(f"start fetching queue: {THORCHAIN_QUEUE_URL}")
                async with session.get(THORCHAIN_QUEUE_URL) as resp:
                    resp = await resp.json()
                    swap_queue = int(resp.get('swap', 0))
                    outbound_queue = int(resp.get('outbound', 0))
                    return QueueInfo(swap_queue, outbound_queue)
            except (ValueError, TypeError, IndexError, ZeroDivisionError, KeyError):
                return QueueInfo.error()

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
                logging.error(f'QueueFetcher error: {e}')
            await asyncio.sleep(self.SLEEP_PERIOD)
