from services.jobs.fetch.base import BaseFetcher
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.depcont import DepContainer

BEP2_BLOCK_URL = 'https://api.binance.org/bc/api/v1/blocks/{block}/txs'


class BEP2BlockFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        sleep_period = parse_timespan_to_seconds(deps.cfg.bep2.fetch_period)
        super().__init__(deps, sleep_period)

    async def get_block(self, block_number):
        url = BEP2_BLOCK_URL.format(block=block_number)
        async with self.deps.session.get(url) as resp:
            return await resp.json()

    async def fetch(self):
        return 1
