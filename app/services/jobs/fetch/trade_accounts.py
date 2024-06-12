from collections import defaultdict
from typing import List

from aionode.types import ThorTradeUnits
from services.jobs.fetch.base import BaseFetcher
from services.lib.depcont import DepContainer
from services.lib.utils import parallel_run_in_groups
from services.models.trade_acc import AlertTradeAccount


class TradeAccountFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        period = self.deps.cfg.as_interval('trade_accounts.fetch_period', '1h')
        super().__init__(deps, sleep_period=period)
        self.deps = deps

    async def _get_traders(self, trade_units: List[ThorTradeUnits]):
        return await parallel_run_in_groups([
            self.deps.thor_connector.query_trade_accounts(u.asset)
            for u in trade_units if u.units > 0
        ], group_size=4, delay=0.5)

    async def fetch(self):
        pools = self.deps.price_holder.pool_info_map
        if not pools:
            self.logger.warning('No pool info map yet. Skipping.')
            return

        vault_balances = await self.deps.thor_connector.query_vault()
        trade_units = await self.deps.thor_connector.query_trade_units()
        traders = await self._get_traders(trade_units)

        return AlertTradeAccount.from_trade_units(trade_units, pools, traders, vault_balances)