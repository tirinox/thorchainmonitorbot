from typing import Dict

from aiothornode.types import ThorLastBlock

from services.jobs.fetch.base import BaseFetcher
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.depcont import DepContainer


class LastBlockFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        sleep_period = parse_timespan_to_seconds(deps.cfg.last_block.get('fetch_period', 10))
        super().__init__(deps, sleep_period)

    async def fetch(self) -> Dict[str, ThorLastBlock]:
        data = await self.deps.midgard_connector.request_random_midgard('v2/thorchain/lastblock')
        last_blocks = [ThorLastBlock.from_json(j) for j in data]
        return {last_block.chain: last_block for last_block in last_blocks}
