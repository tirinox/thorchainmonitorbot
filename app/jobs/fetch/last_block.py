from typing import Dict

from api.aionode.types import ThorLastBlock
from jobs.fetch.base import BaseFetcher
from lib.date_utils import parse_timespan_to_seconds
from lib.depcont import DepContainer


class LastBlockFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        sleep_period = parse_timespan_to_seconds(deps.cfg.last_block.get('fetch_period', 10))
        super().__init__(deps, sleep_period)

    async def fetch(self) -> Dict[str, ThorLastBlock]:
        last_blocks = await self.deps.thor_connector.query_last_blocks()
        return {last_block.chain: last_block for last_block in last_blocks}
