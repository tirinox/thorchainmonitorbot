from typing import Dict

from aiothornode.types import ThorChainInfo

from services.jobs.fetch.base import BaseFetcher
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.depcont import DepContainer
from services.lib.midgard.urlgen import get_url_gen_by_network_id


class ChainStateFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        sleep_period = parse_timespan_to_seconds(deps.cfg.chain_state.fetch_period)
        super().__init__(deps, sleep_period)
        self.url_gen = get_url_gen_by_network_id(deps.cfg.network_id)

    async def fetch(self) -> Dict[str, ThorChainInfo]:
        chain_info = await self.deps.thor_connector.query_chain_info()
        return chain_info
