from typing import List

from jobs.fetch.base import BaseFetcher
from lib.date_utils import parse_timespan_to_seconds
from lib.depcont import DepContainer
from models.node_info import NodeInfo, NetworkNodes


class NodeInfoFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        sleep_period = parse_timespan_to_seconds(deps.cfg.node_info.fetch_period)
        super().__init__(deps, sleep_period)

    async def fetch(self) -> List[NodeInfo]:
        nodes: NetworkNodes = await self.deps.node_cache.get()
        return nodes.node_info_list
