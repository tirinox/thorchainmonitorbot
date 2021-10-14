from aiothornode.types import ThorQueue

from services.jobs.fetch.base import BaseFetcher
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.depcont import DepContainer
from services.models.queue import QueueInfo


class QueueFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        period = parse_timespan_to_seconds(deps.cfg.queue.fetch_period)
        super().__init__(deps, period)

    async def fetch(self) -> QueueInfo:  # override
        resp: ThorQueue = await self.deps.thor_connector.query_queue()
        if resp is None:
            self.logger.error(f'No queue data from THORnodes!')
            return QueueInfo.error()

        q = QueueInfo(
            int(resp.swap),
            int(resp.outbound),
            int(resp.internal)
        )
        return q
