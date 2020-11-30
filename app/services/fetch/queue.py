import aiohttp

from services.fetch.base import BaseFetcher
from services.lib.datetime import parse_timespan_to_seconds
from services.lib.depcont import DepContainer
from services.models.queue import QueueInfo
from services.models.time_series import TimeSeries


class QueueFetcher(BaseFetcher):
    QUEUE_TIME_SERIES = 'thor_queue'

    def __init__(self, deps: DepContainer):
        period = parse_timespan_to_seconds(deps.cfg.queue.fetch_period)
        super().__init__(deps, period)
        self.last_node_ip = None

    async def handle_error(self, e):  # override
        if self.last_node_ip:
            await self.deps.thor_man.blacklist_node(self.last_node_ip)
            self.last_node_ip = None
        return await super().handle_error(e)

    @staticmethod
    def queue_url(base_url):
        return f'{base_url}/thorchain/queue'

    async def fetch(self) -> QueueInfo:  # override
        async with aiohttp.ClientSession() as session:
            if not self.last_node_ip:
                self.last_node_ip = await self.deps.thor_man.select_node()

            queue_url = self.queue_url(self.deps.thor_man.connection_url(self.last_node_ip))

            self.logger.info(f"start fetching queue: {queue_url}")
            async with session.get(queue_url) as resp:
                resp = await resp.json()
                swap_queue = int(resp.get('swap', 0))
                outbound_queue = int(resp.get('outbound', 0))

                ts = TimeSeries(self.QUEUE_TIME_SERIES, self.deps.db)
                await ts.add(swap_queue=swap_queue, outbound_queue=outbound_queue)

                # return QueueInfo(0, 0)  # debug
                return QueueInfo(swap_queue, outbound_queue)
