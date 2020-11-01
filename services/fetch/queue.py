import random
from abc import ABC
from dataclasses import dataclass
from time import time

import aiohttp

from services.config import Config, DB
from services.fetch.base import BaseFetcher

FALLBACK_THORCHAIN_IP = '18.159.173.48'
THORCHAIN_QUEUE_URL = lambda ip: f'http://{ip if ip else FALLBACK_THORCHAIN_IP}:1317/thorchain/queue'


THORCHAIN_SEED_URL = 'https://chaosnet-seed.thorchain.info/'  # all addresses


NODE_REFRESH_TIME = 60 * 60 * 24


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
    def __init__(self, cfg: Config, db: DB, sleep_period=60):
        super().__init__(cfg, db, sleep_period)
        self.node_ip = None
        self.last_ip_time = 0.0

    async def on_error(self, e):
        self.node_ip = None
        async with aiohttp.ClientSession() as session:
            await self.update_connected_node(session)

    async def update_connected_node(self, session):
        if self.node_ip is not None:
            return

        self.logger.info(f"update_connected_node from seed = {THORCHAIN_SEED_URL}")
        async with session.get(THORCHAIN_SEED_URL) as resp:
            resp = await resp.json()
            self.node_ip = random.choice(resp) if resp else FALLBACK_THORCHAIN_IP
            self.last_ip_time = time()
            self.logger.info(f"updated node_ip = {self.node_ip} (t = {int(self.last_ip_time)})")

    async def fetch(self) -> QueueInfo:
        async with aiohttp.ClientSession() as session:
            await self.update_connected_node(session)

            queue_url = THORCHAIN_QUEUE_URL(self.node_ip)
            self.logger.info(f"start fetching queue: {queue_url}")
            async with session.get(queue_url) as resp:
                resp = await resp.json()
                swap_queue = int(resp.get('swap', 0))
                outbound_queue = int(resp.get('outbound', 0))
                # return QueueInfo(0, 0)  # debug
                return QueueInfo(swap_queue, outbound_queue)


class QueueFetcherMock(QueueFetcher, ABC):
    def __init__(self, results):
        self.results = results
        self._it = iter(results)

    async def fetch(self) -> QueueInfo:
        return next(self._it)