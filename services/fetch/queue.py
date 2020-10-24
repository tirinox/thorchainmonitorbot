import random
from abc import ABC
from dataclasses import dataclass

import aiohttp

from services.fetch.base import BaseFetcher

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


class QueueFetcher(BaseFetcher, ABC):
    async def fetch(self) -> QueueInfo:
        async with aiohttp.ClientSession() as session:
            self.logger.info(f"get seed: {THORCHAIN_SEED_URL}")
            async with session.get(THORCHAIN_SEED_URL) as resp:
                resp = await resp.json()
                ip_addr = random.choice(resp) if resp else FALLBACK_THORCHAIN_IP

            queue_url = THORCHAIN_QUEUE_URL(ip_addr)
            self.logger.info(f"start fetching queue: {queue_url}")
            async with session.get(queue_url) as resp:
                resp = await resp.json()
                swap_queue = int(resp.get('swap', 0))
                outbound_queue = int(resp.get('outbound', 0))
                return QueueInfo(swap_queue, outbound_queue)


class QueueFetcherMock(QueueFetcher, ABC):
    def __init__(self, results):
        self.results = results
        self._it = iter(results)

    async def fetch(self) -> QueueInfo:
        return next(self._it)