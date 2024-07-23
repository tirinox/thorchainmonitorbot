from typing import List, Optional

from aionode.types import ThorTradeUnits, ThorBalances, ThorCoin
from services.jobs.fetch.base import BaseFetcher
from services.jobs.volume_recorder import TxCountRecorder, VolumeRecorder, TxCountStats
from services.lib.constants import RUNE_DECIMALS
from services.lib.date_utils import DAY
from services.lib.depcont import DepContainer
from services.lib.utils import parallel_run_in_groups
from services.models.trade_acc import AlertTradeAccountStats, TradeAccountVaults, TradeAccountStats


class TradeAccountFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        period = deps.cfg.as_interval('trade_accounts.summary.fetch_period', '1h')
        tally_period = deps.cfg.as_interval('trade_accounts.summary.tally_period', '7d')
        super().__init__(deps, sleep_period=period)
        self.deps = deps
        self.tally_period = tally_period

    async def _get_traders(self, trade_units: List[ThorTradeUnits], height):
        traders_list = await parallel_run_in_groups([
            self.deps.thor_connector.query_trade_accounts(u.asset, height=height)
            for u in trade_units if u.units > 0
        ], group_size=4, delay=0.5)

        return {traders[0].asset: traders for traders in traders_list}

    async def get_token_balance(self, address: str) -> ThorBalances:
        balances = await self.deps.thor_connector.query_balance(address)
        return balances

    async def get_trade_account_balance(self, address: str) -> List[ThorCoin]:
        """
        Get only trade account balances for the given address
        """
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
        """
        Get all balances for the given address including trade account balances and normal balances
        """
        balances = await self.get_token_balance(address)
        if with_trade_account:
            trade_account_balances = await self.get_trade_account_balance(address)
            balances.assets.extend(trade_account_balances)
        return balances

    async def load_summary_for_height(self, height=0) -> Optional[TradeAccountVaults]:
        if not height:
            pools = self.deps.price_holder.pool_info_map
            if not pools:
                self.logger.error('No pool info map yet. Skipping.')
                return
        else:
            pools = await self.deps.pool_fetcher.load_pools(height)
            # this fills asset prices in usd
            pools = self.deps.price_holder.clone().update(pools).pool_info_map

        vault_balances = await self.deps.thor_connector.query_vault(height=height)
        trade_units = await self.deps.thor_connector.query_trade_units(height)
        traders = await self._get_traders(trade_units, height)
        return TradeAccountVaults.from_trade_units(trade_units, pools, traders, vault_balances)

    @property
    def previous_block_height(self):
        return self.deps.last_block_store.block_time_ago(self.tally_period)

    async def fetch(self) -> AlertTradeAccountStats:
        # State of Trade Account vaults
        current: TradeAccountVaults = await self.load_summary_for_height()
        previous: TradeAccountVaults = await self.load_summary_for_height(self.previous_block_height)
        if not previous:
            self.logger.warning(f'No previous Trade Acc summary data at #{self.previous_block_height}')

        # Volume stats
        volume_recorder: VolumeRecorder = self.deps.volume_recorder
        curr_volume_stats, prev_volume_stats = await volume_recorder.get_previous_and_current_sum(self.tally_period)

        # Transaction count stats
        tally_days = int(self.tally_period / DAY)
        tx_counter: TxCountRecorder = self.deps.tx_count_recorder
        tx_count_stats: TxCountStats = await tx_counter.get_stats(tally_days)

        return AlertTradeAccountStats(
            curr=TradeAccountStats(tx_count_stats.curr, curr_volume_stats, current),
            prev=TradeAccountStats(tx_count_stats.prev, prev_volume_stats, previous),
        )
