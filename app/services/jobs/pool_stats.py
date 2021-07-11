import logging
from typing import List

from services.jobs.fetch.base import INotified, WithDelegates
from services.jobs.fetch.pool_price import PoolPriceFetcher
from services.lib.constants import STABLE_COIN_POOLS
from services.lib.depcont import DepContainer
from services.models.pool_info import PoolInfo
from services.models.pool_stats import LiquidityPoolStats
from services.models.tx import LPAddWithdrawTx, ThorTx, ThorTxType


class PoolStatsUpdater(WithDelegates, INotified):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.logger = logging.getLogger(__name__)

    async def on_data(self, sender, txs: List[ThorTx]):
        # filter by type (+, - only)
        add_withdraw_txs = [tx for tx in txs if tx.type in (ThorTxType.TYPE_WITHDRAW, ThorTxType.TYPE_ADD_LIQUIDITY)]
        # transform
        add_withdraw_txs = [LPAddWithdrawTx.load_from_thor_tx(tx) for tx in add_withdraw_txs]

        await self._update_pools(add_withdraw_txs)
        await self.handle_data(add_withdraw_txs, sender=(sender, self))

    async def _update_pools(self, txs: List[LPAddWithdrawTx]):
        ppf: PoolPriceFetcher = self.deps.price_pool_fetcher
        # we need here most relevant pool state to estimate % of pool after TX
        pool_info_map = await ppf.reload_global_pools()

        await self._load_stats(txs)

        updated_stats = set()
        for tx in txs:
            pool_info: PoolInfo = pool_info_map.get(tx.pool)

            asset_per_rune = pool_info.asset_per_rune if pool_info else 0.0
            full_rune = tx.calc_full_rune_amount(asset_per_rune)  # this one fills rune_volume of each TX

            stats: LiquidityPoolStats = self.pool_stat_map.get(tx.pool)
            if stats:
                stats.update(full_rune, 100)
                updated_stats.add(tx.pool)

        for pool_name in updated_stats:
            pool_stat: LiquidityPoolStats = self.pool_stat_map[pool_name]
            pool_info: PoolInfo = pool_info_map.get(pool_name)
            if pool_info:
                pool_stat.usd_depth = pool_info.usd_depth(self.deps.price_holder.usd_per_rune)
                await pool_stat.write_time_series(self.deps.db)
                await pool_stat.save(self.deps.db)

        if updated_stats:
            self.logger.info(f'pool stats updated for {", ".join(updated_stats)}')

    async def _load_stats(self, txs):
        pool_info_map = self.deps.price_holder.pool_info_map
        if not pool_info_map:
            raise LookupError("pool_info_map is not loaded into the price holder!")

        pool_names = LPAddWithdrawTx.collect_pools(txs)
        pool_names.update(set(STABLE_COIN_POOLS))  # don't forget stable coins, for total usd volume!
        self.pool_stat_map = {
            pool: (await LiquidityPoolStats.get_from_db(pool, self.deps.db)) for pool in pool_names
        }
