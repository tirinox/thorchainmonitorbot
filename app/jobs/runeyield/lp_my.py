import asyncio
import datetime
import operator
from collections import defaultdict, Counter
from typing import List, Tuple, Dict, Optional

from api.midgard.parser import get_parser_by_network_id
from jobs.fetch.tx import TxFetcher
from jobs.runeyield import AsgardConsumerConnectorBase
from jobs.runeyield.base import YieldSummary
from jobs.runeyield.date2block import DateToBlockMapper
from lib.constants import thor_to_float, Chains
from lib.date_utils import days_ago_noon, now_ts
from lib.depcont import DepContainer
from lib.utils import pairwise
from models.asset import Asset
from models.lp_info import LiquidityPoolReport, LiquidityInOutSummary, FeeReport, ReturnMetrics, \
    LPDailyGraphPoint, LPDailyChartByPoolDict, LPPosition
from models.memo import ActionType
from models.pool_info import PoolInfoMap, PoolInfo, pool_share
from models.pool_member import PoolMemberDetails
from models.price import PriceHolder
from models.tx import ThorAction

HeightToAllPools = Dict[int, PoolInfoMap]

BLOCK_ILP_DEPRECATION = 9_450_000


class HomebrewLPConnector(AsgardConsumerConnectorBase):
    def __init__(self, deps: DepContainer):
        super().__init__(deps)
        self.tx_fetcher = TxFetcher(deps)
        self.parser = get_parser_by_network_id(deps.cfg.network_id)
        self.days_for_chart = 30
        self.block_mapper = DateToBlockMapper(deps)
        self.withdraw_fee_rune = 2.0
        self.last_block = 0

    async def generate_yield_summary(self, address, pools: List[str]) -> YieldSummary:
        self.update_fees()

        user_txs = await self._get_user_tx_actions(address)

        if not pools:
            pools = await self.get_my_pools(address)
            pools = [p.pool for p in pools]

        historic_all_pool_states = await self._fetch_historical_pool_states(user_txs)

        reports = []
        for pool_name in pools:
            this_pool_txs = [tx for tx in user_txs if tx.first_pool == pool_name]

            # todo: full membership info is available from get_my_pools! Use it!
            if Asset.from_string(pool_name).is_synth:
                # Savers position
                liq_report = await self._get_savers_position(historic_all_pool_states, pool_name, this_pool_txs,
                                                             address)
            else:
                # Normal liquidity position
                liq_report = await self._create_lp_report_single(historic_all_pool_states, pool_name, this_pool_txs,
                                                                 address)

            reports.append(liq_report)

        weekly_charts = await self._get_charts(user_txs, days=self.days_for_chart)
        return YieldSummary(reports, weekly_charts)

    async def generate_yield_report_single_pool(self, address, pool_name, user_txs=None) -> LiquidityPoolReport:
        self.update_fees()

        user_txs = await self._get_user_tx_actions(address, pool_name) if not user_txs else user_txs
        historic_all_pool_states = await self._fetch_historical_pool_states(user_txs)

        if Asset.from_string(pool_name).is_synth:
            # Savers position
            return await self._get_savers_position(historic_all_pool_states, pool_name, user_txs, address)
        else:
            # Normal liquidity position
            return await self._create_lp_report_single(historic_all_pool_states, pool_name, user_txs, address)

    async def get_my_pools(self, address) -> List[PoolMemberDetails]:
        return await self.deps.midgard_connector.query_pool_membership(address)

    # ------------------------------------------------------------------------------------------------------------------

    KEY_CONST_FEE_OUTBOUND = 'OutboundTransactionFee'
    KEY_CONST_FULL_IL_PROTECTION_BLOCKS = 'FullImpLossProtectionBlocks'

    def update_fees(self):
        withdraw_fee_rune = self.deps.mimir_const_holder.get_constant(self.KEY_CONST_FEE_OUTBOUND, default=2000000)
        self.withdraw_fee_rune = thor_to_float(int(withdraw_fee_rune))

    async def _create_lp_report_single(self,
                                       historic_all_pool_states: HeightToAllPools,
                                       pool_name: str,
                                       user_txs: List[ThorAction],
                                       address) -> LiquidityPoolReport:
        # todo: idea: check date_last_added, if it is not changed - get user_txs from local cache
        # todo: or you can compare current liq_units! if it has changed, you reload tx! (unsafe)

        summary = self._get_liquidity_in_out_summary(user_txs, pool_name, historic_all_pool_states,
                                                     withdraw_fee_rune=self.withdraw_fee_rune)
        liq = await self.get_current_liquidity_from_node(address, pool_name)

        ph = await self.deps.pool_cache.get()

        fees = self._get_fee_report(user_txs, pool_name, historic_all_pool_states, ph)

        usd_per_asset_start, usd_per_rune_start = self._get_earliest_prices(user_txs, historic_all_pool_states)

        pool_info = ph.pool_info_map.get(summary.pool)

        liq_report = LiquidityPoolReport(
            liq,
            ph.usd_per_asset(summary.pool),
            ph.usd_per_rune,
            usd_per_asset_start, usd_per_rune_start,
            in_out=summary, fees=fees,
            pool=pool_info,
        )
        return liq_report

    async def _get_savers_position(self, historic_all_pool_states, pool, user_txs, address):
        summary = self._get_liquidity_in_out_summary(user_txs, pool, historic_all_pool_states,
                                                     withdraw_fee_rune=self.withdraw_fee_rune)
        usd_per_asset_start, usd_per_rune_start = self._get_earliest_prices(user_txs, historic_all_pool_states)

        l1_pool = Asset.to_L1_pool_name(summary.pool)
        ph = await self.deps.pool_cache.get()
        pool_info = ph.pool_info_map.get(l1_pool)

        liq = await self.get_current_liquidity_from_node(address, pool)

        liq_report = LiquidityPoolReport(
            liq,
            ph.usd_per_asset(l1_pool),
            ph.usd_per_rune,
            usd_per_asset_start, usd_per_rune_start,
            in_out=summary,
            fees=FeeReport(),
            pool=pool_info,
        )
        return liq_report

    @staticmethod
    def _find_thor_address_in_tx_list(txs: List[ThorAction]) -> str:
        thor_addresses = (tx.input_thor_address for tx in txs)
        thor_addresses = list(filter(bool, thor_addresses))
        if thor_addresses:
            counter = Counter(thor_addresses)
            top = counter.most_common(1)[0][0]
            return top
        return ''

    @staticmethod
    def is_lp_grandfathered(txs: List[ThorAction], pool: str = '') -> bool:
        for tx in txs:
            if tx.is_of_type(ActionType.ADD_LIQUIDITY):
                if pool and tx.first_pool == pool:
                    if tx.height >= BLOCK_ILP_DEPRECATION:
                        return True
        return False

    @staticmethod
    def _apply_pool_filter(txs: List[ThorAction], pool_filter=None) -> List[ThorAction]:
        if pool_filter:
            return [tx for tx in txs if pool_filter == tx.first_pool]
        else:
            return txs

    async def _get_user_tx_actions(self, address: str, pool_filter=None) -> List[ThorAction]:
        txs = await self.tx_fetcher.fetch_all_tx(address, liquidity_change_only=True)

        txs = self._apply_pool_filter(txs, pool_filter)

        if Chains.detect_chain(address) != Chains.THOR:
            # It is not THOR address! So perhaps there are not all TXS!
            self.logger.info('It is not THOR address. I must find it and load its Txs too!')

            thor_address = self._find_thor_address_in_tx_list(txs)

            if thor_address:
                self.logger.info(f'Found THOR address: "{thor_address}" for asset address: "{address}".')

                txs_from_thor_address = await self.tx_fetcher.fetch_all_tx(thor_address, liquidity_change_only=True)
                txs_from_thor_address = self._apply_pool_filter(txs_from_thor_address, pool_filter)

                old_txs_len = len(txs)
                new_txs_len = len(txs_from_thor_address)

                txs = set(txs) | set(txs_from_thor_address)
                txs = list(txs)

                self.logger.info(f"It has {new_txs_len} Txs, "
                                 f"while the original address {address!r} has {old_txs_len} txs. "
                                 f"After merging there are {len(txs)} txs left.")
            else:
                self.logger.info(f'Not found THOR address for "{address}".')

        txs.sort(key=operator.attrgetter('height'))

        # if the used withdrew 100% of liquidity, we ignore this history.
        # so accounting starts only with the most recent addition

        full_tx_count = len(txs)
        txs = self.cut_off_previous_lp_sessions(txs)
        last_session_tx_count = len(txs)
        if last_session_tx_count != full_tx_count:
            self.logger.warning(f'[{address}]@[POOL:{pool_filter}] has interrupted session: '
                                f'{last_session_tx_count} of {full_tx_count} txs will be processed.')

        return txs

    async def _fetch_historical_pool_states(self, txs: List[ThorAction]) -> HeightToAllPools:
        heights = list(set(tx.height for tx in txs))
        tasks = [self.deps.pool_cache.load_pools(h, caching=True) for h in heights]
        pool_states = await asyncio.gather(*tasks)
        return dict(zip(heights, pool_states))

    def _get_liquidity_in_out_summary(self, txs: List[ThorAction],
                                      pool_name,
                                      pool_historic: HeightToAllPools,
                                      withdraw_fee_rune) -> LiquidityInOutSummary:
        first_add_date, last_add_date = 0, 0
        total_added_as_rune, total_withdrawn_as_rune = 0.0, 0.0
        total_added_as_usd, total_withdrawn_as_usd = 0.0, 0.0
        total_added_as_asset, total_withdrawn_as_asset = 0.0, 0.0

        asset_added, asset_withdrawn = 0.0, 0.0
        rune_added, rune_withdrawn = 0.0, 0.0

        l1_pool_name = Asset.to_L1_pool_name(pool_name)

        for tx in txs:
            tx_timestamp = tx.date_timestamp
            first_add_date = min(first_add_date, tx_timestamp) if first_add_date else tx_timestamp
            last_add_date = max(last_add_date, tx_timestamp) if last_add_date else tx_timestamp

            pools_info: PoolInfoMap = pool_historic[tx.height]
            usd_per_rune = self._calculate_weighted_rune_price_in_usd(pools_info)

            # fixme: block has final state after all TX settled. this_asset_pool_info may be None!
            # so this_asset_pool_info is a real object, but 1/1:1 values inside.
            this_asset_pool_info = self._get_pool(pool_historic, tx.height, l1_pool_name)

            if tx.is_of_type(ActionType.ADD_LIQUIDITY):
                runes = tx.sum_of_rune(in_only=True)
                assets = tx.sum_of_asset(pool_name, in_only=True)

                asset_added += assets
                rune_added += runes

                total_this_runes = runes + this_asset_pool_info.runes_per_asset * assets

                total_added_as_rune += total_this_runes
                total_added_as_usd += total_this_runes * usd_per_rune
                total_added_as_asset += assets + this_asset_pool_info.asset_per_rune * runes
            else:
                half_fee = withdraw_fee_rune * 0.5
                runes = tx.sum_of_rune(out_only=True) + half_fee
                assets = tx.sum_of_asset(pool_name, out_only=True) + half_fee * this_asset_pool_info.asset_per_rune

                asset_withdrawn += assets
                rune_withdrawn += runes

                total_this_runes = runes + this_asset_pool_info.runes_per_asset * assets

                total_withdrawn_as_rune += total_this_runes
                total_withdrawn_as_usd += total_this_runes * usd_per_rune
                total_withdrawn_as_asset += assets + this_asset_pool_info.asset_per_rune * runes

        liquidity_units = self.final_liquidity(txs)

        return LiquidityInOutSummary(
            pool=pool_name,
            rune_added=rune_added,
            asset_added=asset_added,
            pool_units=liquidity_units,
            asset_withdrawn=asset_withdrawn,
            rune_withdrawn=rune_withdrawn,
            total_added_as_asset=total_added_as_asset,
            total_added_as_rune=total_added_as_rune,
            total_added_as_usd=total_added_as_usd,
            total_withdrawn_as_asset=total_withdrawn_as_asset,
            total_withdrawn_as_rune=total_withdrawn_as_rune,
            total_withdrawn_as_usd=total_withdrawn_as_usd,
            first_add_ts=first_add_date,
            last_add_ts=int(last_add_date),
        )

    async def get_current_liquidity_from_node(self, address: str, pool_name: str) -> LPPosition:
        """
        Fetches liquidity data from the node directly. This is a fallback method if the data from the transaction
        history is not available.
        """
        pool_name = Asset.to_L1_pool_name(pool_name).upper()
        ph = await self.deps.pool_cache.get()
        pool_info = ph.find_pool(pool_name)
        usd_per_rune = ph.usd_per_rune

        state = await self.deps.thor_connector.query_liquidity_provider(pool_name, address)

        return LPPosition.create(pool_info, state.units, usd_per_rune)

    def _calculate_weighted_rune_price_in_usd(self, pool_map: PoolInfoMap) -> Optional[float]:
        ph = PriceHolder(self.deps.pool_cache.stable_coins)
        price = ph.calculate_rune_price_here(pool_map)
        if not price:
            raise ValueError('No USD price can be extracted. Perhaps USD pools are missing at that point')
        return price

    def _get_earliest_prices(self, txs: List[ThorAction], pool_historic: HeightToAllPools) \
            -> Tuple[Optional[float], Optional[float]]:
        if not txs:
            return None, None

        earliest_tx = txs[0]
        for tx in txs[1:]:
            if tx.height < earliest_tx.height:
                earliest_tx = tx

        earliest_pools = pool_historic.get(earliest_tx.height)

        usd_per_rune = self._calculate_weighted_rune_price_in_usd(earliest_pools)

        this_pool = earliest_pools.get(Asset.to_L1_pool_name(earliest_tx.first_pool))

        if this_pool is None:
            return None, None

        usd_per_asset = usd_per_rune * this_pool.runes_per_asset

        return usd_per_asset, usd_per_rune

    def _create_lp_position(self, pool, height, my_units: int, pool_historic: HeightToAllPools) -> LPPosition:
        all_pool_info_at_height = pool_historic.get(height)

        pool_info = self._get_pool(pool_historic, height, pool)

        usd_per_rune = self._calculate_weighted_rune_price_in_usd(all_pool_info_at_height)

        return LPPosition.create(pool_info, my_units, usd_per_rune)

    def _create_final_lp_position(self, pool, my_units: int, ph: PriceHolder) -> LPPosition:
        pool_info = ph.find_pool(pool)
        usd_per_rune = ph.usd_per_rune
        return LPPosition.create(pool_info, my_units, usd_per_rune)

    @staticmethod
    def _update_units(units, tx: ThorAction):
        if tx.is_of_type(ActionType.ADD_LIQUIDITY):
            units += tx.meta_add.liquidity_units_int
        elif tx.is_of_type(ActionType.WITHDRAW):
            units += tx.meta_withdraw.liquidity_units_int
        return units

    def _get_fee_report(self,
                        txs: List[ThorAction],
                        pool: str,
                        pool_historic: HeightToAllPools,
                        ph: PriceHolder):

        if not txs:
            return FeeReport(pool)  # empty

        # metrics (fee, imp loss, etc) accumulator
        return_metrics = ReturnMetrics()

        # pairs of position (same lp units) between each add/withdraw tx of the user
        position_pairs: List[Tuple[LPPosition, LPPosition]] = []

        units = 0
        for tx0, tx1 in pairwise(txs):
            tx0: ThorAction
            tx1: ThorAction
            units = self._update_units(units, tx0)

            # User quit completely and entered again
            if units <= 0:
                self.logger.warning(f'{tx0.sender_address} completely withdrawn assets. resetting his positions!')
                position_pairs = []
            else:
                p0 = self._create_lp_position(pool, tx0.height, units, pool_historic)
                p1 = self._create_lp_position(pool, tx1.height, units, pool_historic)
                position_pairs.append((p0, p1))

        # add the last window from the latest tx to the present moment
        last_tx = txs[-1]
        units = self._update_units(units, last_tx)
        position_pairs.append((
            self._create_lp_position(pool, last_tx.height, units, pool_historic),
            self._create_final_lp_position(pool, units, ph)
        ))

        # collect and accumulate all metrics
        for p0, p1 in position_pairs:
            return_metrics += ReturnMetrics.from_position_window(p0, p1)

        # some aux calculations for FeeReport
        current_pool = ph.find_pool(pool)
        curr_usd_per_rune = ph.usd_per_rune
        curr_usd_per_asset = curr_usd_per_rune * current_pool.runes_per_asset

        # fixme: negative fee!
        return_metrics.fees_usd = max(0.0, return_metrics.fees_usd)

        fee_rune = return_metrics.fees_usd / curr_usd_per_rune  # this
        fee_asset = return_metrics.fees_usd / curr_usd_per_asset  # or this, not a SUM!

        return FeeReport(asset=pool,
                         imp_loss_usd=return_metrics.imp_loss,
                         imp_loss_percent=return_metrics.imp_loss_percentage,
                         fee_usd=return_metrics.fees_usd,
                         fee_rune=fee_rune,
                         fee_asset=fee_asset)

    def _pool_units_by_day(self, txs: List[ThorAction], now=None, days=14) -> List:
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

    async def get_last_thorchain_block(self):
        self.last_block = await self.deps.last_block_cache.get_thor_block()
        return self.last_block

    async def _get_charts(self,
                          txs: List[ThorAction],
                          days=14) -> LPDailyChartByPoolDict:

        tx_by_pool_map = defaultdict(list)
        for tx in txs:
            tx_by_pool_map[tx.first_pool].append(tx)

        self.last_block = await self.get_last_thorchain_block()
        results = {}
        now = datetime.datetime.now()

        for pool, pool_txs in tx_by_pool_map.items():
            day_to_units = self._pool_units_by_day(pool_txs, days=days)  # List of (day_no, timestamp, units)

            graph_points = []
            for day, ts, units in day_to_units:
                that_day = now - datetime.timedelta(days=day)
                height = await self.block_mapper.get_block_height_by_date(that_day.date(), self.last_block)
                pools_at_height = await self.deps.pool_cache.load_pools(height, caching=True)
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

    @staticmethod
    def _get_last_deposit_height(txs: List[ThorAction]) -> int:
        last_deposit_height = -1
        for tx in txs:
            if tx.is_of_type(ActionType.ADD_LIQUIDITY):
                if last_deposit_height < tx.height:
                    last_deposit_height = tx.height
        return last_deposit_height

    @staticmethod
    def calculate_imp_loss(pool: PoolInfo, liquidity_units: int, r0: float, a0: float) -> float:
        r1, a1 = pool_share(pool.balance_rune, pool.balance_asset, liquidity_units, pool.units)
        r1, a1 = thor_to_float(r1), thor_to_float(a1)
        coverage = (r0 - r1) + (a0 - a1) * r1 / a1
        return max(0.0, coverage)

    @staticmethod
    def calculate_imp_loss_v58(pool: PoolInfo, liquidity_units: int, r0: float, a0: float) -> float:
        # https://gitlab.com/thorchain/thornode/-/blob/develop/x/thorchain/withdraw_v58.go#L176
        # https://gitlab.com/thorchain/thornode/-/merge_requests/1796
        r1, a1 = pool_share(pool.balance_rune, pool.balance_asset, liquidity_units, pool.units)
        r1, a1 = thor_to_float(r1), thor_to_float(a1)
        if a1 != 0:
            p1 = r1 / a1
            deposit_value = a0 * p1 + r0
            redeem_value = a1 * p1 + r1
        else:
            deposit_value = r0
            redeem_value = r1
        coverage = deposit_value - redeem_value
        return max(0.0, coverage)

    def _get_deposit_values_r0_and_a0(self, txs: List[ThorAction],
                                      historic_all_pool_states: HeightToAllPools,
                                      pool_name: str) -> (float, float):
        """
        r0 = runeDepositValue // the deposit value of the rune received
        a0 = assetDepositValue // the deposit value of the asset received
        """
        r0, a0 = 0.0, 0.0
        units = 0
        for tx in txs:
            if tx.is_of_type(ActionType.ADD_LIQUIDITY):
                pool = self._get_pool(historic_all_pool_states, tx.height, pool_name)
                r, a = pool.get_share_rune_and_asset(tx.meta_add.liquidity_units_int)
                r0 += r
                a0 += a
                units += tx.meta_add.liquidity_units_int
            elif tx.is_of_type(ActionType.WITHDRAW):
                delta_units = abs(tx.meta_withdraw.liquidity_units_int)
                part_ratio = delta_units / units
                units -= delta_units
                r0 -= r0 * part_ratio
                a0 -= a0 * part_ratio

        return r0, a0

    @staticmethod
    def _get_pool(historic_all_pool_states: HeightToAllPools, height, pool_name: str) -> PoolInfo:
        pools = historic_all_pool_states.get(int(height), {})
        pool = pools.get(pool_name)
        return pool or PoolInfo(pool_name, 1, 1, 1, PoolInfo.STAGED)

    @staticmethod
    def final_liquidity(txs: List[ThorAction]):
        lp = 0
        for tx in txs:
            if tx.is_of_type(ActionType.ADD_LIQUIDITY):
                lp += tx.meta_add.liquidity_units_int
            elif tx.is_of_type(ActionType.WITHDRAW):
                lp += tx.meta_withdraw.liquidity_units_int
        return lp

    @staticmethod
    def cut_off_previous_lp_sessions(txs: List[ThorAction]):
        lp = defaultdict(float)  # track LP units for each pool
        new_txs = []
        for tx in txs:
            pool = tx.first_pool
            if tx.is_of_type(ActionType.ADD_LIQUIDITY):
                lp[pool] += tx.meta_add.liquidity_units_int
            elif tx.is_of_type(ActionType.WITHDRAW):
                lp[pool] += tx.meta_withdraw.liquidity_units_int

            new_txs.append(tx)

            if lp[pool] <= 0:
                # oops! user has withdrawn all funds completely: resetting the accumulator!
                new_txs = []
                lp[pool] = 0
        return new_txs
