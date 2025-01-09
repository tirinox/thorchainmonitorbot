import asyncio
from typing import List, Optional

from jobs.fetch.base import BaseFetcher
from jobs.fetch.fair_price import RuneMarketInfoFetcher
from jobs.fetch.pool_price import PoolInfoFetcherMidgard
from lib.async_cache import AsyncTTL
from lib.constants import thor_to_float
from lib.depcont import DepContainer
from lib.utils import a_result_cached
from models.asset import normalize_asset
from models.savers import SaverVault, AlertSaverStats, SaversBank, VNXSaversStats, MidgardSaversHistory


class SaversStatsFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        sleep_period = deps.cfg.as_interval('saver_stats.fetch_period', '10m')
        super().__init__(deps, sleep_period)
        self._pool_source = PoolInfoFetcherMidgard(self.deps, 0)
        self._anti_spam_sleep = 0.5

    @staticmethod
    def calc_saver_return(savers_depth, savers_units, old_savers_depth, old_savers_units, period):
        saver_before_growth = float(old_savers_depth) / float(old_savers_units)
        saver_growth = float(savers_depth) / float(savers_units)
        return ((saver_growth - saver_before_growth) / saver_before_growth) * (356 / period)

    def convert(self, stats: VNXSaversStats, new=True):
        amount = thor_to_float(stats.savers_depth)
        amount_old = thor_to_float(stats.savers_depth_old)
        amount_usd = stats.asset_price * amount
        amount_usd_old = stats.asset_price * amount_old

        max_synth_per_asset_ratio = self.deps.mimir_const_holder.get_max_synth_per_pool_depth()  # normally: 0.6

        cap = stats.pool.get_synth_cap_in_asset_float(max_synth_per_asset_ratio)
        rune_earned = thor_to_float(stats.earned) * stats.asset_price / stats.usd_per_rune
        rune_earned_old = thor_to_float(stats.earned_old) * stats.asset_price / stats.usd_per_rune

        savers_return = stats.saver_return if new and stats.saver_return else stats.saver_return_old

        return SaverVault(
            asset=stats.asset,
            number_of_savers=stats.savers_count if new else stats.savers_count_old,
            total_asset_saved=amount if new else amount_old,
            total_asset_saved_usd=amount_usd if new else amount_usd_old,
            apr=savers_return * 100.0,
            asset_cap=cap,
            runes_earned=rune_earned if new else rune_earned_old,
            synth_supply=thor_to_float(stats.synth_supply),
            pool=stats.pool,
        )

    @staticmethod
    def make_bank(vaults: List[SaverVault]):
        n = 0
        for v in vaults:
            n += v.number_of_savers
        return SaversBank(n, vaults)

    async def load_stats_now(self) -> dict[str, VNXSaversStats]:
        mimir_max_synth_per_pool_depth = self.deps.mimir_const_holder.get_max_synth_per_pool_depth()

        supplies = await self.deps.rune_market_fetcher.get_supply_fetcher().get_all_native_token_supplies()
        supplies = {
            normalize_asset(s['denom']).upper(): int(s['amount']) for s in supplies
        }

        # all_earnings = await self.deps.midgard_connector.query_earnings(count=30, interval='day')
        all_earnings = await self.deps.midgard_connector.query_earnings()
        # 1 day before
        prev_earnings = await self.deps.midgard_connector.query_earnings(count=2, interval='day')

        pools = await self._pool_source.get_pool_info_midgard(period='7d')
        all_saver_pools = [
            pool for pool in pools.values() if pool.savers_depth > 0
        ]

        saver_pools = {}

        for pool in all_saver_pools:
            savers_history: Optional[MidgardSaversHistory] = None
            for _ in range(3):
                savers_history = await self.deps.midgard_connector.query_savers_history(
                    pool.asset, count=9, interval='day'
                )
                if savers_history is not None:
                    break
                else:
                    self.logger.warning(f'Failed to fetch savers history for {pool.asset}')
            if not savers_history:
                self.logger.error(f'Failed to fetch savers history for {pool.asset}!')
                continue

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

            current_earnings_pool = [p for p in all_earnings.meta.pools if p.pool == pool.asset][0]
            old_earnings_pool = [p for p in prev_earnings.intervals[0].pools if p.pool == pool.asset][0]

            # not sure, but I think this is the correct way to calculate the earnings
            prev_earnings_val = current_earnings_pool.saver_earning - old_earnings_pool.saver_earning

            saver_pools[pool.asset] = VNXSaversStats(
                asset=pool.asset,
                saver_return=pool.savers_apr,
                saver_return_old=old_savers_return,
                earned=current_earnings_pool.saver_earning,
                earned_old=prev_earnings_val,
                filled=filled,
                savers_count=savers_history.meta.end_savers_count,
                savers_count_old=savers_history.intervals[-1].savers_count,
                savers_depth=pool.savers_depth,
                savers_depth_old=savers_history.intervals[-1].savers_depth,
                synth_supply=synth_supply,
                asset_price=pool.usd_per_asset,
                asset_depth=pool.balance_asset,
                pool=pool,
            )

            await asyncio.sleep(self._anti_spam_sleep)

        return saver_pools

    async def get_savers_event(self, *_) -> AlertSaverStats:
        vnx_vaults = await self.load_stats_now()
        vaults = [self.convert(v) for v in vnx_vaults.values()]
        curr_saver = self.make_bank(vaults)
        old_vaults = [self.convert(v, new=False) for v in vnx_vaults.values()]
        prev_state = self.make_bank(old_vaults)
        return AlertSaverStats(prev_state, curr_saver)

    CACHE_TTL = 60

    # @AsyncTTL(time_to_live=CACHE_TTL)
    @a_result_cached(CACHE_TTL)
    async def get_savers_event_cached(self) -> AlertSaverStats:
        return await self.get_savers_event()

    async def fetch(self) -> AlertSaverStats:
        return await self.get_savers_event_cached()
