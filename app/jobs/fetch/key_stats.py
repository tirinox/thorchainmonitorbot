import asyncio
import datetime
from typing import List

from api.aionode.types import thor_to_float
from jobs.fetch.base import BaseFetcher
from jobs.fetch.cached.pool import PoolCache
from jobs.fetch.pol import POLAndRunePoolFetcher
from jobs.scanner.swap_routes import SwapRouteRecorder
from jobs.user_counter import UserCounterMiddleware
from jobs.volume_recorder import VolumeRecorder, TxCountRecorder
from lib.constants import BTC_SYMBOL, ETH_SYMBOL
from lib.date_utils import parse_timespan_to_seconds, DAY, HOUR, date_parse_rfc
from lib.depcont import DepContainer
from lib.logs import WithLogger
from models.affiliate import AffiliateInterval, AffiliateCollector
from models.asset import Asset
from models.earnings_history import EarningHistoryResponse, EarningsTuple, IncomeDistribution, \
    build_income_distribution
from models.key_stats_model import AlertKeyStats, KeyStats, LockedValue, SwapRouteEntry
from models.pool_info import PoolInfoMap
from models.vol_n import TxCountStats


class KeyStatsFetcher(BaseFetcher, WithLogger):
    def __init__(self, deps: DepContainer):
        sleep_period = parse_timespan_to_seconds(deps.cfg.key_metrics.fetch_period)
        super().__init__(deps, sleep_period)
        self.tally_days_period = deps.cfg.as_int('key_metrics.tally_period_days', 7)

        self._swap_route_recorder = SwapRouteRecorder(deps.db)
        self._runepool = POLAndRunePoolFetcher(deps)

    @property
    def tally_period_in_sec(self):
        return self.tally_days_period * DAY

    async def fetch(self) -> AlertKeyStats:
        # Find block height a week ago
        previous_block = await self.deps.last_block_cache.get_thor_block_time_ago(self.tally_period_in_sec)

        if previous_block < 0:
            raise ValueError(f'Previous block is negative {previous_block}!')

        # Load pool data for BTC/ETH value in the pools
        pf: PoolCache = self.deps.pool_cache
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
        curr_swap_vol_usd, prev_swap_vol_usd = mdg_swap_stats.curr_and_prev_interval("total_volume_usd")

        swap_count = await self.get_swap_number_stats()

        # Earnings and who they were accrued to
        start_ts, end_ts = await self.get_tally_period()
        curr_earnings, prev_earnings, income = await self.get_earnings_curr_prev(start_ts, end_ts)

        # Swap routes
        usd_per_rune = await self.deps.pool_cache.get_usd_per_rune()
        routes = await self._swap_route_recorder.get_top_swap_routes_by_volume(
            usd_per_rune,
            self.tally_days_period,
            top_n=10,
            normalize_assets=True,
            reorder_assets=True,
        )
        routes = self.beautify_routes(routes)

        # Affiliates
        top_affiliates, curr_affiliate_revenue, prev_affiliate_revenue = await self.get_top_affiliates(
            start_ts, end_ts)
        # Assign affiliate revenue to earnings
        curr_earnings.affiliate_revenue = curr_affiliate_revenue
        prev_earnings.affiliate_revenue = prev_affiliate_revenue

        # Done. Construct the resulting event
        start = datetime.datetime.fromtimestamp(start_ts, datetime.timezone.utc)
        end = datetime.datetime.fromtimestamp(end_ts, datetime.timezone.utc)
        result = AlertKeyStats(
            routes=routes,
            days=self.tally_days_period,
            current=KeyStats(
                curr_lock,
                curr_swap_vol_dict,
                swap_count.curr,
                swapper_count=user_stats.wau,
                earnings=curr_earnings,
                total_volume_usd=curr_swap_vol_usd,
            ),
            previous=KeyStats(
                prev_lock,
                prev_swap_vol_dict,
                swap_count.prev,
                swapper_count=user_stats.wau_prev_weak,
                earnings=prev_earnings,
                total_volume_usd=prev_swap_vol_usd,
            ),
            swap_type_distribution=distribution,
            start_date=start,
            end_date=end,
            top_affiliates=top_affiliates,
            income=income,
        )
        self.fill_btc_eth_usd_totals(result.current, curr_pools)
        self.fill_btc_eth_usd_totals(result.previous, prev_pools)
        return result

    @staticmethod
    def fill_btc_eth_usd_totals(s: KeyStats, pools: PoolInfoMap):
        s.btc_total_amount = s.btc_total_usd = 0.0
        s.eth_total_amount = s.eth_total_usd = 0.0
        s.usd_total_amount = 0.0

        for pool in pools.values():
            asset = pool.asset
            b = thor_to_float(pool.balance_asset)
            if asset == BTC_SYMBOL:
                s.btc_total_amount += b
                s.btc_total_usd += b * pool.usd_per_asset
            elif asset == ETH_SYMBOL:
                s.eth_total_amount += b
                s.eth_total_usd += b * pool.usd_per_asset
            elif 'USD' in asset or 'DAI-' in asset:  # pretty naive check for stable coins
                s.usd_total_amount += b

    async def get_lock_value(self, sec_ago=0) -> LockedValue:
        height = await self.deps.last_block_cache.get_thor_block_time_ago(sec_ago)

        price_holder = await self.deps.pool_cache.load_as_price_holder(height=height)

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

    async def get_tally_period(self) -> tuple[int, int]:
        """
        [start, end) of the tally period in UTC seconds. It ends at the last full hour before the last block,
        because Midgard reports the hour that is still running as empty.
        """
        block = await self.deps.thor_connector.query_thorchain_block_raw(None)
        try:
            block_time = date_parse_rfc(block['header']['time']).replace(tzinfo=datetime.timezone.utc)
        except (KeyError, TypeError, ValueError, AttributeError):
            raise ConnectionError(f'Failed to load the time of the last block: {str(block)[:200]!r}')

        end_ts = int(block_time.timestamp()) // HOUR * HOUR
        return end_ts - self.tally_period_in_sec, end_ts

    async def get_earnings_curr_prev(self, start_ts: int, end_ts: int) \
            -> tuple[EarningsTuple, EarningsTuple, IncomeDistribution]:
        mdg = self.deps.midgard_connector
        prev_start_ts = start_ts - self.tally_period_in_sec
        curr, prev, last_aggregated_ts = await asyncio.gather(
            mdg.query_earnings(start_ts, end_ts, interval='hour'),
            mdg.query_earnings(prev_start_ts, start_ts, interval='hour'),
            mdg.query_last_aggregated_ts(),
        )
        if not curr or not prev:
            raise ConnectionError('Failed to load earnings history from Midgard')

        income = build_income_distribution(curr.intervals, start_ts, end_ts)
        if last_aggregated_ts < end_ts:
            income.issues.append(f'Midgard is behind: aggregated up to {last_aggregated_ts}, needed {end_ts}')
        prev_income = build_income_distribution(prev.intervals, prev_start_ts, start_ts)
        if prev_income.is_complete:
            income.prev_total_usd = prev_income.total_usd

        if income.issues:
            self.logger.warning(f'Income distribution is incomplete: {income.issues}')
        if income.discrepancy_rune_raw:
            self.logger.warning(f'Income categories do not add up to the total: '
                                f'{income.discrepancy_rune_raw} base units are unaccounted')

        return (
            EarningHistoryResponse.calc_earnings(curr.intervals),
            EarningHistoryResponse.calc_earnings(prev.intervals),
            income,
        )

    async def get_top_affiliates(self, start_ts: int, end_ts: int):
        # without an interval Midgard sums the whole range into a single row, thornames included
        mdg = self.deps.midgard_connector
        prev_start_ts = start_ts - self.tally_period_in_sec
        curr_affiliates, prev_affiliates = await asyncio.gather(
            mdg.query_affiliates(from_ts=start_ts, to_ts=end_ts, interval=''),
            mdg.query_affiliates(from_ts=prev_start_ts, to_ts=start_ts, interval=''),
        )
        if not curr_affiliates or not prev_affiliates:
            raise ConnectionError('Failed to load affiliate history from Midgard')

        prev_week_interval = AffiliateInterval.sum_of_intervals_per_thorname(
            prev_affiliates.intervals).sort_thornames_by_usd_volume()
        curr_week_interval = AffiliateInterval.sum_of_intervals_per_thorname(
            curr_affiliates.intervals).sort_thornames_by_usd_volume()

        prev_names_dict = {tn.thorname: tn for tn in
                           prev_week_interval.thornames} if prev_week_interval.thornames else {}

        # Midgard gives the affiliates' volumeUSD (their fee earnings) in cents: Int64(e2) in its spec
        curr_aff_revenue = curr_week_interval.volume_usd / 100
        prev_aff_revenue = prev_week_interval.volume_usd / 100
        top_affiliates = []

        ns = self.deps.name_service

        for affiliate in curr_week_interval.thornames:
            prev_record = prev_names_dict.get(affiliate.thorname)
            top_affiliates.append(AffiliateCollector(
                total_usd=affiliate.volume_usd / 100,
                prev_total_usd=(prev_record.volume_usd / 100 if prev_record else 0.0),
                thorname=affiliate.thorname,
                display_name=ns.get_affiliate_name(affiliate.thorname),
                count=affiliate.count,
                prev_count=(prev_record.count if prev_record else 0),
                logo=ns.aff_man.get_affiliate_logo(affiliate.thorname, with_local_prefix=True),
            ))

        return top_affiliates, curr_aff_revenue, prev_aff_revenue

    @staticmethod
    def beautify_routes(routes: List[SwapRouteEntry]):
        collectors = []
        for obj in routes:
            from_name = Asset(obj.from_asset).shortest
            to_name = Asset(obj.to_asset).shortest
            # collectors[(obj.from_asset, obj.to_asset)] += obj.volume_rune
            collectors.append(
                SwapRouteEntry(from_asset=from_name, to_asset=to_name, volume_rune=obj.volume_rune,
                               volume_usd=obj.volume_usd)
            )
        collectors.sort(key=lambda r: r.volume_usd, reverse=True)
        return collectors
