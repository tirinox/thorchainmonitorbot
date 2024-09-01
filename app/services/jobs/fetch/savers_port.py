import asyncio

from services.jobs.fetch.base import BaseFetcher
from services.jobs.fetch.fair_price import RuneMarketInfoFetcher
from services.jobs.fetch.pool_price import PoolInfoFetcherMidgard
from services.lib.depcont import DepContainer
from services.lib.utils import a_result_cached
from services.models.asset import normalize_asset
from services.models.savers import VNXSaversStats, MidgardSaversHistory


class SaverStatsPortedFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        sleep_period = deps.cfg.as_interval('saver_stats.fetch_period', '10m')
        super().__init__(deps, sleep_period)
        self._pool_source = PoolInfoFetcherMidgard(self.deps, 0)
        self._supply_fetcher = RuneMarketInfoFetcher(self.deps)
        self._anti_spam_sleep = 0.5

    @staticmethod
    def calc_saver_return(savers_depth, savers_units, old_savers_depth, old_savers_units, period):
        saver_before_growth = float(old_savers_depth) / float(old_savers_units)
        saver_growth = float(savers_depth) / float(savers_units)
        return ((saver_growth - saver_before_growth) / saver_before_growth) * (356 / period)

    async def fetch(self) -> dict[str, VNXSaversStats]:
        return await self.load_stats_cached()

    @a_result_cached(ttl=60)
    async def load_stats_cached(self) -> dict[str, VNXSaversStats]:
        return await self.load_stats_now()

    async def load_stats_now(self) -> dict[str, VNXSaversStats]:
        mimir_max_synth_per_pool_depth = self.deps.mimir_const_holder.get_max_synth_per_pool_depth()

        supplies = await self._supply_fetcher.get_supply_fetcher().get_all_native_token_supplies()
        supplies = {
            normalize_asset(s['denom']).upper(): int(s['amount']) for s in supplies
        }

        all_earnings = await self.deps.midgard_connector.query_earnings()
        last_daily_earnings = await self.deps.midgard_connector.query_earnings(count=2, interval='day')

        pools = await self._pool_source.get_pool_info_midgard(period='7d')
        all_saver_pools = [
            pool for pool in pools.values() if pool.savers_depth > 0
        ]

        saver_pools = {}

        for pool in all_saver_pools:
            savers_history: MidgardSaversHistory = await self.deps.midgard_connector.query_savers_history(
                pool.asset, count=9, interval='day'
            )

            synth_cap = 2.0 * mimir_max_synth_per_pool_depth * pool.balance_asset
            synth_supply = supplies.get(pool.asset, 0)
            if synth_supply:
                filled = synth_supply / synth_cap
            else:
                filled = pool.savers_depth / synth_cap

            old_savers_return = self.calc_saver_return(
                savers_history.intervals[-1].savers_depth,
                savers_history.intervals[-1].savers_units,
                savers_history.intervals[0].savers_depth,
                savers_history.intervals[0].savers_units,
                period=7
            )

            all_earnings_pool = [p for p in all_earnings.meta.pools if p.pool == pool.asset][0]
            earned_old_pool = [p for p in last_daily_earnings.intervals[0].pools if p.pool == pool.asset][0]

            saver_pools[pool.asset] = VNXSaversStats(
                asset=pool.asset,
                saver_return=pool.savers_apr,
                saver_return_old=old_savers_return,
                earned=all_earnings_pool.saver_earning,
                earned_old=earned_old_pool.saver_earning,
                filled=filled,
                savers_count=savers_history.meta.end_savers_count,
                savers_count_old=savers_history.intervals[-1].savers_count,
                savers_depth=pool.savers_depth,
                savers_depth_old=savers_history.intervals[-1].savers_depth,
                synth_supply=synth_supply,
                asset_price=pool.usd_per_asset,
                asset_depth=pool.balance_asset,
            )

            await asyncio.sleep(self._anti_spam_sleep)

        return saver_pools
