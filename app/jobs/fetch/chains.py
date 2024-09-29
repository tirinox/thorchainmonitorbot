from typing import Dict

from api.aionode.types import ThorChainInfo
from jobs.fetch.base import BaseFetcher
from lib.date_utils import parse_timespan_to_seconds
from lib.depcont import DepContainer


class ChainStateFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        sleep_period = parse_timespan_to_seconds(deps.cfg.chain_halt_state.fetch_period)
        super().__init__(deps, sleep_period)

    async def fetch(self) -> Dict[str, ThorChainInfo]:
        chain_info = await self.deps.thor_connector.query_chain_info()
        return chain_info
