import logging
from typing import List

from services.jobs.fetch.base import INotified, WithDelegates
from services.lib.constants import STABLE_COIN_POOLS
from services.lib.depcont import DepContainer
from services.models.pool_info import PoolInfo
from services.models.pool_stats import StakePoolStats
from services.models.tx import StakeTx, ThorTx, ThorTxType


class PoolStatsUpdater(WithDelegates, INotified):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.logger = logging.getLogger(__name__)

    async def on_data(self, sender, txs: List[ThorTx]):
        add_withdraw_txs = [tx for tx in txs if tx.type in (ThorTxType.TYPE_WITHDRAW, ThorTxType.TYPE_ADD_LIQUIDITY)]
        add_withdraw_txs = [StakeTx.load_from_thor_tx(tx) for tx in add_withdraw_txs]
        await self._load_stats(add_withdraw_txs)
        await self._update_pools(add_withdraw_txs)
        await self.handle_data(add_withdraw_txs, sender=sender)

    async def _update_pools(self, txs: List[StakeTx]):
        updated_stats = set()
        result_txs = []

        for tx in txs:
            price = self.pool_info_map.get(tx.pool, PoolInfo.dummy()).price
            stats: StakePoolStats = self.pool_stat_map.get(tx.pool)
            if price and stats:
                full_rune = tx.calc_full_rune_amount(price)
                stats.update(full_rune, 100)
                updated_stats.add(tx.pool)
                result_txs.append(tx)

        self.logger.info(f'pool stats updated for {", ".join(updated_stats)}')

        for pool_name in updated_stats:
            pool_stat: StakePoolStats = self.pool_stat_map[pool_name]
            pool_info: PoolInfo = self.pool_info_map.get(pool_name)
            pool_stat.usd_depth = pool_info.usd_depth(self.deps.price_holder.usd_per_rune)
            await pool_stat.write_time_series(self.deps.db)
            await pool_stat.save(self.deps.db)

        return result_txs

    async def _load_stats(self, txs):
        self.pool_info_map = self.deps.price_holder.pool_info_map
        if not self.pool_info_map:
            raise LookupError("pool_info_map is not loaded into the price holder!")

        pool_names = StakeTx.collect_pools(txs)
        pool_names.update(set(STABLE_COIN_POOLS))  # don't forget BUSD, for total usd volume!
        self.pool_stat_map = {
            pool: (await StakePoolStats.get_from_db(pool, self.deps.db)) for pool in pool_names
        }
