from typing import Dict

from aionode.types import ThorChainInfo

from services.jobs.fetch.base import BaseFetcher
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.depcont import DepContainer


class ChainStateFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        sleep_period = parse_timespan_to_seconds(deps.cfg.chain_state.fetch_period)
        super().__init__(deps, sleep_period)

    async def fetch(self) -> Dict[str, ThorChainInfo]:
        chain_info = await self.deps.thor_connector.query_chain_info()
        return chain_info
