import asyncio
import datetime
import operator
from collections import defaultdict
from typing import List, Tuple, Dict, Optional

from services.jobs.fetch.pool_price import PoolPriceFetcher
from services.jobs.fetch.runeyield import AsgardConsumerConnectorBase
from services.jobs.fetch.runeyield.base import YieldSummary
from services.jobs.fetch.runeyield.date2block import DateToBlockMapper
from services.jobs.fetch.tx import TxFetcher
from services.lib.constants import THOR_DIVIDER_INV, STABLE_COIN_POOLS, NetworkIdents
from services.lib.date_utils import days_ago_noon, now_ts
from services.lib.depcont import DepContainer
from services.lib.midgard.parser import get_parser_by_network_id
from services.lib.midgard.urlgen import MidgardURLGenBase
from services.lib.money import weighted_mean
from services.lib.utils import pairwise
from services.models.lp_info import LiquidityPoolReport, CurrentLiquidity, FeeReport, ReturnMetrics, LPDailyGraphPoint, \
    LPDailyChartByPoolDict
from services.models.pool_info import LPPosition, PoolInfoMap
from services.models.pool_member import PoolMemberDetails
from services.models.tx import ThorTx, ThorTxType

HeightToAllPools = Dict[int, PoolInfoMap]

DEFAULT_RUNE_PRICE = 10.0  # USD


class HomebrewLPConnector(AsgardConsumerConnectorBase):
    def __init__(self, deps: DepContainer, ppf: PoolPriceFetcher, url_gen: MidgardURLGenBase):
        super().__init__(deps, ppf, url_gen)
        self.tx_fetcher = TxFetcher(deps)
        self.parser = get_parser_by_network_id(deps.cfg.network_id)
        self.use_thor_consensus = False
        self.days_for_chart = 14
        self.max_attempts = 5
        self.block_mapper = DateToBlockMapper(deps)

    async def generate_yield_summary(self, address, pools: List[str]) -> Tuple[dict, List[LiquidityPoolReport]]:
        user_txs = await self._get_user_tx_actions(address)

        # On Midgard V1 we must manually get list of Lpools
        if not NetworkIdents.is_multi(self.deps.cfg.network_id) and not pools:
            pools = await self.get_my_pools(address)

        historic_all_pool_states, current_pools_details = await asyncio.gather(
            self._fetch_historical_pool_states(user_txs),
            self._get_details_of_staked_pools(address, pools)
        )

        d = self.deps
        reports = []
        for pool_details in current_pools_details.values():
            this_pool_txs = [tx for tx in user_txs if tx.first_pool == pool_details.pool]
            liq = self._get_current_liquidity(this_pool_txs, pool_details, historic_all_pool_states)
            fees = self._get_fee_report(this_pool_txs, pool_details, historic_all_pool_states)
            usd_per_asset_start, usd_per_rune_start = self._get_earliest_prices(this_pool_txs, historic_all_pool_states)
            stake_report = LiquidityPoolReport(
                d.price_holder.usd_per_asset(liq.pool),
                d.price_holder.usd_per_rune,
                usd_per_asset_start, usd_per_rune_start,
                liq, fees=fees,
                pool=d.price_holder.pool_info_map.get(liq.pool)
            )
            reports.append(stake_report)

        weekly_charts = await self._get_charts(user_txs, days=self.days_for_chart)
        return YieldSummary(reports, weekly_charts)

    async def generate_yield_report_single_pool(self, address, pool) -> LiquidityPoolReport:
        # todo: idea: check date_last_added, if it is not changed - get user_txs from local cache
        # todo: or you can compare current liq_units! if it has changed, you reload tx!

        user_txs = await self._get_user_tx_actions(address, pool)

        historic_all_pool_states, current_pools_details = await asyncio.gather(
            self._fetch_historical_pool_states(user_txs),
            self._get_details_of_staked_pools(address, pool)
        )

        # filter only 1 pool
        current_pool_details: PoolMemberDetails = current_pools_details.get(pool)

        cur_liq = self._get_current_liquidity(user_txs, current_pool_details, historic_all_pool_states)

        fees = self._get_fee_report(user_txs, current_pool_details, historic_all_pool_states)
        usd_per_asset_start, usd_per_rune_start = self._get_earliest_prices(user_txs, historic_all_pool_states)

        d = self.deps
        stake_report = LiquidityPoolReport(
            d.price_holder.usd_per_asset(cur_liq.pool),
            d.price_holder.usd_per_rune,
            usd_per_asset_start, usd_per_rune_start,
            cur_liq, fees=fees,
            pool=d.price_holder.pool_info_map.get(cur_liq.pool)
        )
        return stake_report

    async def get_my_pools(self, address) -> List[str]:
        url = self.url_gen.url_for_address_pool_membership(address)
        self.logger.info(f'get: {url}')
        async with self.deps.session.get(url) as resp:
            if resp.status == 404:
                raise FileNotFoundError
            j = await resp.json()
            return self.parser.parse_pool_membership(j)

    # ------------------------------------------------------------------------------------------------------------------

    async def _get_user_tx_actions(self, address: str, pool_filter=None) -> List[ThorTx]:
        txs = await self.tx_fetcher.fetch_user_tx(address, liquidity_change_only=True)
        if pool_filter:
            txs = [tx for tx in txs if pool_filter == tx.first_pool]
        txs.sort(key=operator.attrgetter('height_int'))
        return txs

    async def _fetch_historical_pool_states(self, txs: List[ThorTx]) -> HeightToAllPools:
        heights = list(set(tx.height_int for tx in txs))
        thor_conn = self.deps.thor_connector

        # make sure, that connections are fresh, in order not to update it at all the height simultaneously
        await thor_conn._get_random_clients()

        tasks = [self.ppf.get_current_pool_data_full(h, caching=True) for h in heights]
        pool_states = await asyncio.gather(*tasks)
        return dict(zip(heights, pool_states))

    async def _get_details_of_staked_pools(self, address, pools) -> Dict[str, PoolMemberDetails]:
        url = self.url_gen.url_details_of_pools(address, pools)
        self.logger.info(f'get: {url}')
        async with self.deps.session.get(url) as resp:
            j = await resp.json()
            if 'error' in j:
                raise FileNotFoundError(j['error'])
            pool_array = self.parser.parse_pool_member_details(j, address)
            return {p.pool: p for p in pool_array}

    def _get_current_liquidity(self, txs: List[ThorTx],
                               pool_details: PoolMemberDetails,
                               pool_historic: HeightToAllPools) -> CurrentLiquidity:
        first_state_date, last_stake_date = 0, 0
        total_added_rune, total_withdrawn_rune = 0.0, 0.0
        total_added_usd, total_withdrawn_usd = 0.0, 0.0
        total_added_asset, total_withdrawn_asset = 0.0, 0.0
        fee_earn_usd = 0.0

        for tx in txs:
            tx_timestamp = tx.date_timestamp
            first_state_date = min(first_state_date, tx_timestamp) if first_state_date else tx_timestamp
            last_stake_date = max(last_stake_date, tx_timestamp) if last_stake_date else tx_timestamp

            pools_info: PoolInfoMap = pool_historic[tx.height_int]
            this_asset_pool_info = pools_info.get(pool_details.pool)

            usd_per_rune = self._calculate_weighted_rune_price_in_usd(pools_info, use_default_price=True)

            if tx.type == ThorTxType.TYPE_ADD_LIQUIDITY:
                runes = tx.sum_of_rune(in_only=True)
                assets = tx.sum_of_asset(pool_details.pool, in_only=True)

                total_this_runes = runes + this_asset_pool_info.runes_per_asset * assets

                total_added_rune += total_this_runes
                total_added_usd += total_this_runes * usd_per_rune
                total_added_asset += assets + this_asset_pool_info.asset_per_rune * runes
            else:
                runes = tx.sum_of_rune(out_only=True)
                assets = tx.sum_of_asset(pool_details.pool, out_only=True)

                total_this_runes = runes + this_asset_pool_info.runes_per_asset * assets

                total_withdrawn_rune += total_this_runes
                total_withdrawn_usd += total_this_runes * usd_per_rune
                total_withdrawn_asset += assets + this_asset_pool_info.asset_per_rune * runes

        m = THOR_DIVIDER_INV

        results = CurrentLiquidity(
            pool=pool_details.pool,
            rune_stake=pool_details.rune_added * m,
            asset_stake=pool_details.asset_added * m,
            pool_units=pool_details.liquidity_units,
            asset_withdrawn=pool_details.asset_withdrawn * m,
            rune_withdrawn=pool_details.rune_withdrawn * m,
            total_staked_asset=total_added_asset,
            total_staked_rune=total_added_rune,
            total_staked_usd=total_added_usd,
            total_unstaked_asset=total_withdrawn_asset,
            total_unstaked_rune=total_withdrawn_rune,
            total_unstaked_usd=total_withdrawn_usd,
            first_stake_ts=int(first_state_date),
            last_stake_ts=int(last_stake_date),
            fee_earn_usd=fee_earn_usd,
        )
        return results

    @staticmethod
    def _calculate_weighted_rune_price_in_usd(pool_map: PoolInfoMap, use_default_price=False) -> Optional[float]:
        prices, weights = [], []
        for stable_symbol in STABLE_COIN_POOLS:
            pool_info = pool_map.get(stable_symbol)
            if pool_info and pool_info.balance_rune > 0 and pool_info.asset_per_rune > 0:
                prices.append(pool_info.asset_per_rune)
                weights.append(pool_info.balance_rune)

        if prices:
            return weighted_mean(prices, weights)
        elif use_default_price:
            return DEFAULT_RUNE_PRICE  # todo: get rune price somewhere else!

    def _get_earliest_prices(self, txs: List[ThorTx], pool_historic: HeightToAllPools) \
            -> Tuple[Optional[float], Optional[float]]:
        if not txs:
            return None, None

        earliest_tx = txs[0]
        for tx in txs[1:]:
            if tx.height_int < earliest_tx.height_int:
                earliest_tx = tx

        earliest_pools = pool_historic.get(earliest_tx.height_int)

        usd_per_rune = self._calculate_weighted_rune_price_in_usd(earliest_pools, use_default_price=True)

        this_pool = earliest_pools.get(earliest_tx.first_pool)
        rune_per_asset = this_pool.runes_per_asset
        usd_per_asset = usd_per_rune * rune_per_asset

        return usd_per_asset, usd_per_rune

    def _create_lp_position(self, pool, height, my_units: int, pool_historic: HeightToAllPools) -> LPPosition:
        all_pool_info_at_height = pool_historic.get(height)
        pool_info = all_pool_info_at_height.get(pool)

        usd_per_rune = self._calculate_weighted_rune_price_in_usd(all_pool_info_at_height, use_default_price=True)

        return LPPosition.create(pool_info, my_units, usd_per_rune)

    def _create_current_lp_position(self, pool, my_units: int) -> LPPosition:
        pool_info = self.deps.price_holder.find_pool(pool)
        usd_per_rune = self.deps.price_holder.usd_per_rune
        return LPPosition.create(pool_info, my_units, usd_per_rune)

    @staticmethod
    def _update_units(units, tx: ThorTx):
        if tx.type == ThorTxType.TYPE_ADD_LIQUIDITY:
            units += tx.meta_add.liquidity_units_int
        elif tx.type == ThorTxType.TYPE_WITHDRAW:
            units += tx.meta_withdraw.liquidity_units_int
        return units

    def _get_fee_report(self,
                        txs: List[ThorTx],
                        pool_details: PoolMemberDetails,
                        pool_historic: HeightToAllPools):

        # metrics (fee, imp loss, etc) accumulator
        return_metrics = ReturnMetrics()
        pool = pool_details.pool

        # pairs of position (same lp units) between each add/withdraw tx of the user
        position_pairs: List[Tuple[LPPosition, LPPosition]] = []

        units = 0
        for tx0, tx1 in pairwise(txs):
            tx0: ThorTx
            tx1: ThorTx
            units = self._update_units(units, tx0)
            p0 = self._create_lp_position(pool, tx0.height_int, units, pool_historic)
            p1 = self._create_lp_position(pool, tx1.height_int, units, pool_historic)
            position_pairs.append((p0, p1))

        # add the last window from the latest tx to the present moment
        last_tx = txs[-1]
        units = self._update_units(units, last_tx)
        position_pairs.append((
            self._create_lp_position(pool, last_tx.height_int, units, pool_historic),
            self._create_current_lp_position(pool, units)
        ))

        # collect and accumulate all metrics
        for p0, p1 in position_pairs:
            return_metrics += ReturnMetrics.from_position_window(p0, p1)

        # some aux calculations for FeeReport
        current_pool = self.deps.price_holder.find_pool(pool_details.pool)

        curr_usd_per_rune = self.deps.price_holder.usd_per_rune
        curr_usd_per_asset = curr_usd_per_rune * current_pool.runes_per_asset

        fee_rune = return_metrics.fees_usd * 0.5 / curr_usd_per_rune
        fee_asset = return_metrics.fees_usd * 0.5 / curr_usd_per_asset

        # fixme: negative fee!
        return FeeReport(asset=pool_details.pool,
                         imp_loss_usd=return_metrics.imp_loss,
                         imp_loss_percent=return_metrics.imp_loss_percentage,
                         fee_usd=return_metrics.fees_usd,
                         fee_rune=fee_rune,
                         fee_asset=fee_asset)

    def _pool_units_by_day(self, txs: List[ThorTx], now=None, days=14) -> List:
        if not txs:
            return [(i, 0) for i in range(days)]  # always 0

        units_history = []
        current_units = 0
        old_ts = 0
        for tx in txs:
            current_units = self._update_units(current_units, tx)
            units_history.append((tx.date_timestamp, current_units))
            assert tx.date_timestamp >= old_ts, "tx list must be sorted"
            old_ts = tx.date_timestamp

        now = now or datetime.datetime.now()
        day_to_units = []

        last_action_ts, current_units = units_history[-1]
        for day in range(days):
            if day:
                day_ago_date_ts = days_ago_noon(day, now).timestamp()  # yesterday + n: noon (for caching purposes)
            else:
                day_ago_date_ts = now_ts()  # exact now

            while day_ago_date_ts < last_action_ts:
                last_action_ts, current_units = units_history.pop() if units_history else (0, 0)

            day_to_units.append((day, day_ago_date_ts, current_units))

        return day_to_units

    async def _get_charts(self,
                          txs: List[ThorTx],
                          days=14) -> LPDailyChartByPoolDict:

        tx_by_pool_map = defaultdict(list)
        for tx in txs:
            tx_by_pool_map[tx.first_pool].append(tx)

        last_block = await self.block_mapper.get_last_thorchain_block()
        results = {}
        now = datetime.datetime.now()
        for pool, pool_txs in tx_by_pool_map.items():
            day_to_units = self._pool_units_by_day(pool_txs, days=days)  # List of (day_no, timestamp, units)

            graph_points = []
            for day, ts, units in day_to_units:
                that_day = now - datetime.timedelta(days=day)
                height = await self.block_mapper.get_block_height_by_date(that_day.date(), last_block)
                pools_at_height = await self.ppf.get_current_pool_data_full(height, caching=True)
                pool_info = pools_at_height.get(pool, None)

                if pool_info:
                    usd_per_rune = self._calculate_weighted_rune_price_in_usd(pools_at_height)
                    total_my_runes = pool_info.total_my_capital_of_pool_in_rune(units)
                    usd_value = total_my_runes * usd_per_rune
                    pt = LPDailyGraphPoint(ts, usd_value)
                else:
                    pt = LPDailyGraphPoint(ts, 0.0)

                graph_points.append(pt)
            results[pool] = list(reversed(graph_points))  # chronologically

        return results
