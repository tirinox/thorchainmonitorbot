from typing import List

from aionode.types import ThorTradeUnits, ThorBalances, ThorCoin
from services.jobs.fetch.base import BaseFetcher
from services.lib.constants import RUNE_DECIMALS
from services.lib.depcont import DepContainer
from services.lib.utils import parallel_run_in_groups
from services.models.trade_acc import AlertTradeAccountSummary


class TradeAccountFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        period = deps.cfg.as_interval('trade_accounts.fetch_period', '1h')
        super().__init__(deps, sleep_period=period)
        self.deps = deps

    async def _get_traders(self, trade_units: List[ThorTradeUnits]):
        return await parallel_run_in_groups([
            self.deps.thor_connector.query_trade_accounts(u.asset)
            for u in trade_units if u.units > 0
        ], group_size=4, delay=0.5)

    async def get_token_balance(self, address: str) -> ThorBalances:
        balances = await self.deps.thor_connector.query_balance(address)
        return balances

    async def get_trade_account_balance(self, address: str) -> List[ThorCoin]:
        balances = []
        trade_accounts = await self.deps.thor_connector.query_trade_account(address)
        for trade_account in trade_accounts:
            balances.append(ThorCoin(
                trade_account.asset,
                trade_account.units,
                RUNE_DECIMALS
            ))
        return balances

    async def get_whole_balances(self, address: str, with_trade_account=True) -> ThorBalances:
        balances = await self.get_token_balance(address)
        if with_trade_account:
            trade_account_balances = await self.get_trade_account_balance(address)
            balances.assets.extend(trade_account_balances)
        return balances

    async def fetch(self):
        pools = self.deps.price_holder.pool_info_map
        if not pools:
            self.logger.warning('No pool info map yet. Skipping.')
            return

        vault_balances = await self.deps.thor_connector.query_vault()
        trade_units = await self.deps.thor_connector.query_trade_units()
        traders = await self._get_traders(trade_units)

        return AlertTradeAccountSummary.from_trade_units(trade_units, pools, traders, vault_balances)
