import aiohttp

from services.fetch.base import BaseFetcher
from services.lib.datetime import parse_timespan_to_seconds
from services.lib.depcont import DepContainer
from services.models.queue import QueueInfo


class QueueFetcher(BaseFetcher):
    QUEUE_PATH = '/thorchain/queue'

    def __init__(self, deps: DepContainer):
        period = parse_timespan_to_seconds(deps.cfg.queue.fetch_period)
        super().__init__(deps, period)

    async def fetch(self) -> QueueInfo:  # override
        async with aiohttp.ClientSession() as session:
            # return QueueInfo(50, 0)  # debug

            resp = await self.deps.thor_nodes.request(self.QUEUE_PATH)
            if resp is None:
                return QueueInfo.error()

            swap_queue = int(resp.get('swap', 0))
            outbound_queue = int(resp.get('outbound', 0))

            return QueueInfo(swap_queue, outbound_queue)
