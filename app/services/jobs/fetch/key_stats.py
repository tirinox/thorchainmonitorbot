import asyncio
import datetime
from collections import defaultdict
from typing import List

from aionode.types import thor_to_float
from services.jobs.fetch.base import BaseFetcher
from services.jobs.fetch.pol import RunePoolFetcher
from services.jobs.fetch.pool_price import PoolFetcher
from services.jobs.scanner.swap_routes import SwapRouteRecorder
from services.jobs.user_counter import UserCounterMiddleware
from services.jobs.volume_recorder import VolumeRecorder, TxCountRecorder
from services.lib.date_utils import parse_timespan_to_seconds, DAY
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger
from services.models.earnings_history import EarningsInterval
from services.models.key_stats_model import AlertKeyStats, KeyStats, LockedValue, AffiliateCollectors
from services.models.vol_n import TxCountStats

FS_AFFILIATES_API_URL = "https://flipsidecrypto.xyz/api/v1/queries/cebb9137-b58f-452d-a30a-6990a8e8fdc8/data/latest"


class KeyStatsFetcher(BaseFetcher, WithLogger):
    def __init__(self, deps: DepContainer):
        sleep_period = parse_timespan_to_seconds(deps.cfg.key_metrics.fetch_period)
        super().__init__(deps, sleep_period)
        self.tally_days_period = deps.cfg.as_int('key_metrics.tally_period_days', 7)

        self._swap_route_recorder = SwapRouteRecorder(deps.db)
        self._runepool = RunePoolFetcher(deps)

        # x3 days (this week + previous week + spare days)
        self.trim_max_days = deps.cfg.as_int('key_metrics.trim_max_days', self.tally_days_period * 3)

    @property
    def tally_period_in_sec(self):
        return self.tally_days_period * DAY

    async def fetch(self) -> AlertKeyStats:
        # Find block height a week ago
        previous_block = self.deps.last_block_store.block_time_ago(self.tally_period_in_sec)

        if previous_block < 0:
            raise ValueError(f'Previous block is negative {previous_block}!')

        # Load pool data for BTC/ETH value in the pools
        pf: PoolFetcher = self.deps.pool_fetcher
        curr_pools, prev_pools = await asyncio.gather(
            pf.load_pools(),
            pf.load_pools(height=previous_block)
        )

        curr_pools = pf.convert_pool_list_to_dict(list(curr_pools.values()))
        prev_pools = pf.convert_pool_list_to_dict(list(prev_pools.values()))

        # TC's locked asset value
        prev_lock, curr_lock = await asyncio.gather(
            self.get_lock_value(self.tally_period_in_sec),
            self.get_lock_value()
        )

        # Swapper count
        user_counter: UserCounterMiddleware = self.deps.user_counter
        user_stats = await user_counter.get_main_stats()

        # Swap volumes (trade, synth, normal)
        prev_swap_vol_dict, curr_swap_vol_dict, distribution, mdg_swap_stats = await self.get_swap_volume_stats()
        swap_count = await self.get_swap_number_stats()

        # Earnings
        (
            (curr_total_earnings, curr_block_earnings, curr_organic_fees),
            (prev_total_earnings, prev_block_earnings, prev_organic_fees),
        ) = await self.get_earnings_curr_prev()

        # Swap routes
        routes = await self._swap_route_recorder.get_top_swap_routes_by_volume(
            self.tally_days_period,
            top_n=10,
            normalize_assets=True,
            reorder_assets=True,
        )

        # Affiliates
        affiliates = await self.get_affiliates_from_flipside()
        top_affiliates = self.calc_top_affiliates(affiliates)
        curr_aff_usd, prev_aff_usd = self.calc_total_affiliate_curr_prev(affiliates)

        # Rune pool depths:
        curr_runepool = await self._runepool.load_runepool()
        prev_runepool = await self._runepool.load_runepool(self.tally_period_in_sec)
        runepool_depth = curr_runepool.providers.current_deposit_float if curr_runepool else 0.0
        runepool_prev_depth = prev_runepool.providers.current_deposit_float if prev_runepool else 0.0

        # Done. Construct the resulting event
        end = datetime.datetime.utcnow()
        start = end - datetime.timedelta(days=self.tally_days_period)
        return AlertKeyStats(
            routes=routes,
            days=self.tally_days_period,
            current=KeyStats(
                curr_pools,
                curr_lock,
                curr_swap_vol_dict,
                swap_count.curr,
                swapper_count=user_stats.wau,
                affiliate_revenue_usd=curr_aff_usd,
                block_rewards_usd=curr_block_earnings,
                fee_rewards_usd=curr_organic_fees,
                protocol_revenue_usd=curr_total_earnings,
            ),
            previous=KeyStats(
                prev_pools,
                prev_lock,
                prev_swap_vol_dict,
                swap_count.prev,
                swapper_count=user_stats.wau_prev_weak,
                affiliate_revenue_usd=prev_aff_usd,
                block_rewards_usd=prev_block_earnings,
                fee_rewards_usd=prev_organic_fees,
                protocol_revenue_usd=prev_total_earnings,
            ),
            runepool_depth=runepool_depth,
            runepool_prev_depth=runepool_prev_depth,
            swap_type_distribution=distribution,
            start_date=start,
            end_date=end,
            top_affiliates_usd=top_affiliates,
            mdg_swap_stats=mdg_swap_stats,
        )

    async def get_lock_value(self, sec_ago=0) -> LockedValue:
        height = self.deps.last_block_store.block_time_ago(sec_ago)
        pools = await self.deps.pool_fetcher.load_pools(height=height)
        price_holder = self.deps.price_holder.clone().update(pools)

        total_pooled_rune = price_holder.total_pooled_value_rune
        total_pooled_usd = price_holder.total_pooled_value_usd

        nodes = await self.deps.thor_connector.query_node_accounts()
        total_bonded_rune = sum([thor_to_float(node.bond) for node in nodes])
        total_bonded_usd = total_bonded_rune * price_holder.usd_per_rune

        date = datetime.datetime.now() - datetime.timedelta(seconds=sec_ago)

        return LockedValue(
            date,
            total_pooled_rune,
            total_pooled_usd,
            total_bonded_rune,
            total_bonded_usd,
            total_value_locked=total_pooled_rune + total_bonded_rune,
            total_value_locked_usd=total_pooled_usd + total_bonded_usd,
        )

    async def get_swap_volume_stats(self):
        # Recorded Volume stats
        volume_recorder: VolumeRecorder = self.deps.volume_recorder
        seconds = self.tally_period_in_sec
        curr_volume_stats, prev_volume_stats = await volume_recorder.get_previous_and_current_sum(seconds)

        # Recorded distribution
        distribution = await volume_recorder.get_latest_distribution_by_asset_type(seconds)

        # Midgard's Swap volume stats as an exclusive source of truth
        double_period = self.tally_days_period * 2 + 1
        swap_stats = await self.deps.midgard_connector.query_swap_stats(count=double_period)

        return prev_volume_stats, curr_volume_stats, distribution, swap_stats

    async def get_swap_number_stats(self) -> TxCountStats:
        # Transaction count stats
        tx_counter: TxCountRecorder = self.deps.tx_count_recorder
        return await tx_counter.get_stats(self.tally_days_period)

    async def get_affiliates_from_flipside(self):
        async with self.deps.session.get(FS_AFFILIATES_API_URL) as resp:
            if resp.status == 200:
                j = await resp.json()
                aff_collectors = [AffiliateCollectors.from_json(item) for item in j]
                aff_collectors.sort(key=lambda item: item.date, reverse=True)

                if not aff_collectors:
                    self.logger.error(f'No data loaded')
                    self.deps.emergency.report('WeeklyStats',
                                               'No data loaded',
                                               url=FS_AFFILIATES_API_URL)
                    raise IOError('No data from Flipside')

                max_date = aff_collectors[0].date
                if max_date - datetime.datetime.utcnow() > datetime.timedelta(days=2):
                    self.logger.error("FS data is too old")
                    self.deps.emergency.report('WeeklyStats', 'FS Aff data is too old',
                                               date=max_date, url=FS_AFFILIATES_API_URL)
                    raise IOError('Flipside returned outdated rows')

                return aff_collectors

    def calc_top_affiliates(self, aff_collectors: List[AffiliateCollectors]):
        fee_usd_by_label = defaultdict(float)

        unique_dates = set()
        for aff in aff_collectors:
            unique_dates.add(aff.date)
            if len(unique_dates) > self.tally_days_period:
                # enough days!
                break

            fee_usd_by_label[aff.label] += aff.fee_usd

        return dict(sorted(fee_usd_by_label.items(), key=lambda item: item[1], reverse=True))

    def calc_total_affiliate_curr_prev(self, aff_collectors: List[AffiliateCollectors]):
        curr_usd, prev_usd = 0.0, 0.0

        is_curr = True
        unique_dates = set()
        for aff in aff_collectors:
            unique_dates.add(aff.date)
            if len(unique_dates) > self.tally_days_period:
                if is_curr:
                    is_curr = False
                    unique_dates = {aff.date}
                else:
                    break

            if is_curr:
                curr_usd += aff.fee_usd
            else:
                prev_usd += aff.fee_usd

        return curr_usd, prev_usd

    async def get_earnings_curr_prev(self):
        double_period = self.tally_days_period * 2 + 1
        earnings = await self.deps.midgard_connector.query_earnings(count=double_period, interval='day')

        def calc_earnings(intervals: List[EarningsInterval]):
            """liquidityEarnings + bondingEarnings = earnings
            blockRewards +  liquidityFees = earnings"""

            total_earnings = sum(thor_to_float(e.earnings) * e.rune_price_usd for e in intervals)
            block_earnings = sum(thor_to_float(e.block_rewards) * e.rune_price_usd for e in intervals)
            organic_fees = sum(thor_to_float(e.liquidity_fees) * e.rune_price_usd for e in intervals)
            return total_earnings, block_earnings, organic_fees

        return (
            calc_earnings(intervals=earnings.intervals[0:self.tally_days_period]),
            calc_earnings(intervals=earnings.intervals[self.tally_days_period:])
        )
