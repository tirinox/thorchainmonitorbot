import aiohttp
from aiohttp import ClientSession

from services.config import Config
from services.db import DB
from services.fetch.base import BaseFetcher, INotified
from services.fetch.node_ip_manager import ThorNodeAddressManager
from services.models.queue import QueueInfo


class QueueFetcher(BaseFetcher):
    def __init__(self, cfg: Config, db: DB,
                 session: ClientSession,
                 thor_man: ThorNodeAddressManager,
                 delegate: INotified = None):
        super().__init__(cfg, db, session, cfg.queue.fetch_period, delegate)
        self.thor_man = thor_man
        self.last_node_ip = None

    async def handle_error(self, e):  # override
        if self.last_node_ip:
            await self.thor_man.blacklist_node(self.last_node_ip)
            self.last_node_ip = None
        return await super().handle_error(e)

    @staticmethod
    def queue_url(base_url):
        return f'{base_url}/thorchain/queue'

    async def fetch(self) -> QueueInfo:  # override
        async with aiohttp.ClientSession() as session:
            if not self.last_node_ip:
                self.last_node_ip = await self.thor_man.select_node()

            queue_url = self.queue_url(self.thor_man.connection_url(self.last_node_ip))

            self.logger.info(f"start fetching queue: {queue_url}")
            async with session.get(queue_url) as resp:
                resp = await resp.json()
                swap_queue = int(resp.get('swap', 0))
                outbound_queue = int(resp.get('outbound', 0))

                # return QueueInfo(0, 0)  # debug
                return QueueInfo(swap_queue, outbound_queue)
