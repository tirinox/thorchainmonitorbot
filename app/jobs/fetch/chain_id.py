from typing import NamedTuple

from jobs.fetch.base import BaseFetcher
from lib.date_utils import parse_timespan_to_seconds
from lib.depcont import DepContainer
from lib.utils import safe_get


class EventChainId(NamedTuple):
    chain_id: str


class AlertChainIdChange(NamedTuple):
    prev_chain_id: str
    curr_chain_id: str


class ChainIdFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        sleep_period = parse_timespan_to_seconds(deps.cfg.chain_id.fetch_period)
        super().__init__(deps, sleep_period)
        self.step_sleep = deps.cfg.sleep_step

    async def fetch(self):
        thor = self.deps.thor_connector
        status = await thor.query_native_status_raw()
        if not status or not isinstance(status, dict):
            self.logger.error('Failed to get Node status from THORNode')
            return

        net_ident = safe_get(status, 'result', 'node_info', 'network')
        if not net_ident:
            self.logger.error('Failed to get Net Ident from THORNode')
            return

        return EventChainId(net_ident)
