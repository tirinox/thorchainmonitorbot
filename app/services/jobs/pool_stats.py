import logging
from typing import List

from services.jobs.fetch.base import INotified
from services.lib.constants import STABLE_COIN_POOLS
from services.lib.depcont import DepContainer
from services.models.pool_info import PoolInfo
from services.models.pool_stats import StakePoolStats
from services.models.tx import StakeTx, ThorTx


class PoolStatsUpdater(INotified):
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = logging.getLogger(__name__)

    async def on_data(self, sender, txs):
        await self._load_stats(txs)
        await self._update_pools(txs)

    async def _update_pools(self, txs: List[ThorTx]):
        updated_stats = set()
        result_txs = []

        for tx in txs:
            tx: ThorTx
            price = self.pool_info_map.get(tx.pool, PoolInfo.dummy()).price  # fixme
            stats: StakePoolStats = self.pool_stat_map.get(tx.pool)  # fixme
            if price and stats:
                # fixme!!
                full_rune = tx.calc_full_rune_amount(price)
                stats.update(full_rune, 100)
                updated_stats.add(tx.pool)  # fixme
                result_txs.append(tx)

        self.logger.info(f'pool stats updated for {", ".join(updated_stats)}')

        for pool_name in updated_stats:
            pool_stat: StakePoolStats = self.pool_stat_map[pool_name]
            pool_info: PoolInfo = self.pool_info_map.get(pool_name)
            pool_stat.usd_depth = pool_info.usd_depth(self.deps.price_holder.usd_per_rune)
            await pool_stat.write_time_series(self.deps.db)
            await pool_stat.save(self.deps.db)

        self.logger.info(f'new tx to analyze: {len(result_txs)}')

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
