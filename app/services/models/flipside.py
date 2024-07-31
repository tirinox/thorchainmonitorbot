import dataclasses
import operator
from collections import defaultdict
from datetime import datetime
from functools import cached_property
from typing import NamedTuple, List

from services.jobs.fetch.flipside.flipside import FSList, KEY_DATETIME
from services.lib.constants import STABLE_COIN_POOLS_ALL, thor_to_float
from services.models.key_stats_model import SwapRouteEntry
from services.models.pool_info import PoolInfoMap


class FSSwapVolume(NamedTuple):
    date: datetime
    swap_synth_volume_usd: float = 0.0
    swap_non_synth_volume_usd: float = 0.0
    swap_volume_usd: float = 0.0
    swap_volume_usd_cumulative: float = 0.0

    @classmethod
    def from_json(cls, j):
        return cls(
            j.get(KEY_DATETIME),
            float(j.get('SWAP_SYNTH_VOLUME_USD', 0.0)),
            float(j.get('SWAP_NON_SYNTH_VOLUME_USD', 0.0)),
            float(j.get('SWAP_VOLUME_USD', 0.0)),
            float(j.get('SWAP_VOLUME_USD_CUMULATIVE', 0.0)),
        )

    @classmethod
    def from_json_lowercase(cls, j):
        return cls(
            j.get(KEY_DATETIME),
            float(j.get('swap_synth_volume_usd', 0.0)),
            float(j.get('swap_non_synth_volume_usd', 0.0)),
            float(j.get('swap_volume_usd', 0.0)),
            float(j.get('swap_volume_usd_cumulative', 0.0)),
        )


class FSLockedValue(NamedTuple):
    date: datetime
    total_value_pooled: float = 0.0
    total_value_pooled_usd: float = 0.0
    total_value_bonded: float = 0.0
    total_value_bonded_usd: float = 0.0
    total_value_locked: float = 0.0
    total_value_locked_usd: float = 0.0

    @classmethod
    def from_json(cls, j):
        return cls(
            j.get(KEY_DATETIME),
            float(j.get('TOTAL_VALUE_POOLED', 0.0)),
            float(j.get('TOTAL_VALUE_POOLED_USD', 0.0)),
            float(j.get('TOTAL_VALUE_BONDED', 0.0)),
            float(j.get('TOTAL_VALUE_BONDED_USD', 0.0)),
            float(j.get('TOTAL_VALUE_LOCKED', 0.0)),
            float(j.get('TOTAL_VALUE_LOCKED_USD', 0.0)),
        )

    @classmethod
    def from_json_lowercase(cls, j):
        return cls(
            j.get(KEY_DATETIME),
            float(j.get('total_value_pooled', 0.0)),
            float(j.get('total_value_pooled_usd', 0.0)),
            float(j.get('total_value_bonded', 0.0)),
            float(j.get('total_value_bonded_usd', 0.0)),
            float(j.get('total_value_locked', 0.0)),
            float(j.get('total_value_locked_usd', 0.0)),
        )


class FSSwapCount(NamedTuple):
    date: datetime
    swap_count: int = 0
    unique_swapper_count: int = 0
    swap_count_cumulative: int = 0

    @classmethod
    def from_json(cls, j):
        return cls(
            j.get(KEY_DATETIME),
            int(j.get('SWAP_COUNT', 0)),
            int(j.get('UNIQUE_SWAPPER_COUNT', 0) or 0),  # fixme: None!!
            int(j.get('SWAP_COUNT_CUMULATIVE', 0)),
        )

    @classmethod
    def from_json_lowercase(cls, j):
        return cls(
            j.get(KEY_DATETIME),
            int(j.get('swap_count', 0)),
            int(j.get('unique_swapper_count', 0)),
            int(j.get('swap_count_cumulative', 0)),
        )


class FSFees(NamedTuple):
    date: datetime
    liquidity_fees: float = 0.0
    liquidity_fees_usd: float = 0.0
    block_rewards: float = 0.0
    block_rewards_usd: float = 0.0
    pct_of_earnings_from_liq_fees: float = 0.0
    pct_30d_moving_average: float = 0.0
    total_earnings: float = 0.0
    total_earnings_usd: float = 0.0
    earnings_to_nodes: float = 0.0
    earnings_to_nodes_usd: float = 0.0
    earnings_to_pools: float = 0.0
    earnings_to_pools_usd: float = 0.0
    liquidity_fees_usd_cumulative: float = 0.0
    block_rewards_usd_cumulative: float = 0.0
    total_earnings_usd_cumulative: float = 0.0
    earnings_to_nodes_usd_cumulative: float = 0.0
    earnings_to_pools_usd_cumulative: float = 0.0

    @classmethod
    def from_json(cls, j):
        return cls(
            j.get(KEY_DATETIME),
            float(j.get('LIQUIDITY_FEES', 0.0)),
            float(j.get('LIQUIDITY_FEES_USD', 0.0)),
            float(j.get('BLOCK_REWARDS', 0.0)),
            float(j.get('BLOCK_REWARDS_USD', 0.0)),
            float(j.get('PCT_OF_EARNINGS_FROM_LIQ_FEES', 0.0)),
            float(j.get('PCT_30D_MOVING_AVERAGE', 0.0)),
            float(j.get('TOTAL_EARNINGS', 0.0)),
            float(j.get('TOTAL_EARNINGS_USD', 0.0)),
            float(j.get('EARNINGS_TO_NODES', 0.0)),
            float(j.get('EARNINGS_TO_NODES_USD', 0.0)),
            float(j.get('EARNINGS_TO_POOLS', 0.0)),
            float(j.get('EARNINGS_TO_POOLS_USD', 0.0)),
            float(j.get('LIQUIDITY_FEES_USD_CUMULATIVE', 0.0)),
            float(j.get('BLOCK_REWARDS_USD_CUMULATIVE', 0.0)),
            float(j.get('TOTAL_EARNINGS_USD_CUMULATIVE', 0.0)),
            float(j.get('EARNINGS_TO_NODES_USD_CUMULATIVE', 0.0)),
            float(j.get('EARNINGS_TO_POOLS_USD_CUMULATIVE', 0.0)),
        )

    @classmethod
    def from_json_lowercase(cls, j):
        return cls(
            j.get(KEY_DATETIME),
            float(j.get('liquidity_fees', 0.0)),
            float(j.get('liquidity_fees_usd', 0.0)),
            float(j.get('block_rewards', 0.0)),
            float(j.get('block_rewards_usd', 0.0)),
            float(j.get('pct_of_earnings_from_liq_fees', 0.0)),
            float(j.get('pct_30d_moving_average', 0.0)),
            float(j.get('total_earnings', 0.0)),
            float(j.get('total_earnings_usd', 0.0)),
            float(j.get('earnings_to_nodes', 0.0)),
            float(j.get('earnings_to_nodes_usd', 0.0)),
            float(j.get('earnings_to_pools', 0.0)),
            float(j.get('earnings_to_pools_usd', 0.0)),
            float(j.get('liquidity_fees_usd_cumulative', 0.0)),
            float(j.get('block_rewards_usd_cumulative', 0.0)),
            float(j.get('total_earnings_usd_cumulative', 0.0)),
            float(j.get('earnings_to_nodes_usd_cumulative', 0.0)),
            float(j.get('earnings_to_pools_usd_cumulative', 0.0)),
        )


class FSAffiliateCollectors(NamedTuple):
    date: datetime
    label: str
    fee_usd: float = 0.0
    cumulative_fee_usd: float = 0.0
    total_cumulative_fee_usd: float = 0.0

    @classmethod
    def from_json_lowercase(cls, j):
        return cls(
            j.get(KEY_DATETIME),
            j.get('label', ''),
            fee_usd=float(j.get('fee_usd', 0.0)),
            cumulative_fee_usd=float(j.get('cumulative_fee_usd', 0.0)),
            total_cumulative_fee_usd=float(j.get('total_cumulative_fee_usd', 0.0)),
        )

    @classmethod
    def from_json(cls, j):
        return cls(
            j.get(KEY_DATETIME),
            j.get('LABEL', ''),
            fee_usd=float(j.get('FEE_USD', 0.0)),
            cumulative_fee_usd=float(j.get('CUMULATIVE_FEE_USD', 0.0)),
            total_cumulative_fee_usd=float(j.get('TOTAL_CUMULATIVE_FEE_USD', 0.0)),
        )


class FSSwapRoutes(NamedTuple):
    date: datetime
    assets: str
    asset_from: str
    asset_to: str
    swap_count: int
    swap_volume: float
    usd_per_swap: float
    fee_per_swap: float

    @classmethod
    def from_json(cls, j):
        """[{"SWAP_PATH":"BTC.BTC <-> THOR.RUNE","TOTAL_VOLUME_USD":20045361.3515259,"DAY":"2023-04-06"},...]"""
        assets = j.get('SWAP_PATH')
        asset_from, asset_to = assets.split(' <-> ', 2) if assets else ('', '')

        return cls(
            j.get(KEY_DATETIME),
            assets, asset_from, asset_to,
            0,
            float(j.get('TOTAL_VOLUME_USD', 0.0)),
            0,
            0,
        )

    @classmethod
    def from_json_lowercase(cls, j):
        assets = j.get('swap_path')
        asset_from, asset_to = assets.split(' <-> ', 2) if assets else ('', '')

        return cls(
            j.get(KEY_DATETIME),
            assets, asset_from, asset_to,
            0,
            float(j.get('total_volume_usd', 0.0)),
            0,
            0,
        )


@dataclasses.dataclass
class KeyStats:
    pools: PoolInfoMap
    lock: FSLockedValue
    swap_vol: dict
    swap_count: dict
    swapper_count: int


@dataclasses.dataclass
class AlertKeyStats:
    series: FSList
    current: KeyStats
    previous: KeyStats
    routes: List[SwapRouteEntry]
    days: int = 7

    @property
    def end_date(self):
        return self.series.latest_date

    def get_stables_sum(self, previous=False):
        return self.get_sum(STABLE_COIN_POOLS_ALL, previous)

    def get_sum(self, coin_list, previous=False):
        source = self.previous.pools if previous else self.current.pools
        running_sum = 0.0

        for symbol in coin_list:
            pool = source.get(symbol)
            if pool:
                running_sum += pool.balance_asset
        return thor_to_float(running_sum)

    def get_btc(self, previous=False):
        return self.get_sum(('BTC.BTC',), previous)

    def get_eth(self, previous=False):
        return self.get_sum(('ETH.ETH',), previous)

    @property
    def top_affiliate_daily(self):
        daily_list, _ = self.curr_prev_data
        collectors = defaultdict(float)

        for objects_for_day in daily_list:
            for obj in objects_for_day:
                if isinstance(obj, FSAffiliateCollectors):
                    if obj.label:
                        collectors[obj.label] += obj.fee_usd
        return list(sorted(collectors.items(), key=operator.itemgetter(1), reverse=True))

    @property
    def swap_routes(self):
        collectors = defaultdict(float)
        for obj in self.routes:
            collectors[(obj.from_asset, obj.to_asset)] += obj.volume_rune
        return list(sorted(collectors.items(), key=operator.itemgetter(1), reverse=True))

    @cached_property
    def curr_prev_data(self):
        curr_data, prev_data = self.series.get_current_and_previous_range(self.days)
        return curr_data, prev_data

    @cached_property
    def total_revenue_usd_curr_prev(self):
        curr_data, prev_data = self.curr_prev_data
        return sum_by_attribute_pair(curr_data, prev_data, 'total_earnings_usd', FSFees)

    @cached_property
    def block_rewards_usd_curr_prev(self):
        curr_data, prev_data = self.curr_prev_data
        return sum_by_attribute_pair(curr_data, prev_data, 'block_rewards_usd', FSFees)

    @cached_property
    def liquidity_fee_usd_curr_prev(self):
        curr_data, prev_data = self.curr_prev_data
        return sum_by_attribute_pair(curr_data, prev_data, 'liquidity_fees_usd', FSFees)

    @cached_property
    def affiliate_fee_usd_curr_prev(self):
        curr_data, prev_data = self.curr_prev_data
        return sum_by_attribute_pair(curr_data, prev_data, 'fee_usd', FSAffiliateCollectors)

    @cached_property
    def block_ratio(self):
        block_rewards_usd, _ = self.block_rewards_usd_curr_prev
        total_revenue_usd, _ = self.total_revenue_usd_curr_prev
        block_ratio_v = block_rewards_usd / total_revenue_usd if total_revenue_usd else 100.0
        return block_ratio_v

    @cached_property
    def organic_ratio(self):
        total_revenue_usd, _ = self.total_revenue_usd_curr_prev
        liq_fee_usd, _ = self.liquidity_fee_usd_curr_prev
        organic_ratio_v = liq_fee_usd / total_revenue_usd if total_revenue_usd else 100.0
        return organic_ratio_v

    @cached_property
    def swap_count_curr_prev(self):
        curr_data, prev_data = self.curr_prev_data
        swap_count, prev_swap_count = sum_by_attribute_pair(curr_data, prev_data, 'swap_count', FSSwapCount)
        return swap_count, prev_swap_count

    @cached_property
    def usd_volume_curr_prev(self):
        curr_data, prev_data = self.curr_prev_data
        usd_volume, prev_usd_volume = sum_by_attribute_pair(curr_data, prev_data, 'swap_volume_usd', FSSwapVolume)
        return usd_volume, prev_usd_volume

    @property
    def locked_value_usd_curr_prev(self):
        return self.current.lock, self.previous.lock


def sum_by_attribute(daily_list, attr_name, klass=None, f_sum=sum):
    try:
        return f_sum(
            getattr(obj, attr_name)
            for objects_for_day in daily_list
            for obj in objects_for_day
            if not klass or isinstance(obj, klass)
        )
    except ValueError:
        return 0.0  # max of empty sequence


def sum_by_attribute_pair(first_list, second_list, attr_name, klass=None, f_sum=sum):
    return (
        sum_by_attribute(first_list, attr_name, klass, f_sum),
        sum_by_attribute(second_list, attr_name, klass, f_sum)
    )
