import copy
import dataclasses
import logging
from dataclasses import dataclass
from typing import List, Dict, NamedTuple, Optional

import math

from api.aionode.types import ThorPool
from lib.constants import thor_to_float
from lib.money import calc_percent_change
from .asset import Asset
from .earnings_history import EarningHistoryResponse


def pool_share(rune_depth, asset_depth, my_units, pool_total_units):
    if not pool_total_units:
        return 0, 0
    rune_share = (rune_depth * my_units) / pool_total_units
    asset_share = (asset_depth * my_units) / pool_total_units
    return rune_share, asset_share


class PoolUnitsAdjustment(NamedTuple):
    delta_units: int
    new_units: int


@dataclass
class PoolInfo:
    asset: str

    balance_asset: int
    balance_rune: int
    pool_units: int

    status: str

    usd_per_asset: float = 0.0
    pool_apy: float = 0.0
    synth_supply: int = 0
    synth_units: int = 0
    units: int = 0  # synth + pool_units
    volume_24h: int = 0

    savers_depth: int = 0
    savers_units: int = 0
    savers_apr: float = 0.0

    pool_apr: float = 0.0  # new!

    is_virtual: bool = False

    original: Optional[ThorPool] = None

    DEPRECATED_BOOTSTRAP = 'bootstrap'
    DEPRECATED_ENABLED = 'enabled'
    SUSPENDED = 'suspended'
    AVAILABLE = 'available'  # enabled
    STAGED = 'staged'  # bootstrap

    def percent_share(self, runes, correction=0.0):
        full_balance_rune = 2 * thor_to_float(self.balance_rune) + correction
        return runes / full_balance_rune * 100.0

    def get_share_rune_and_asset(self, units: int) -> (float, float):
        r, a = pool_share(self.balance_rune, self.balance_asset, my_units=units, pool_total_units=self.units)
        return thor_to_float(r), thor_to_float(a)

    def total_my_capital_of_pool_in_rune(self, units: int) -> float:
        r, _ = self.get_share_rune_and_asset(units)
        return r * 2.0

    @classmethod
    def dummy(cls):
        return cls('', 1, 1, 1, cls.DEPRECATED_BOOTSTRAP)

    def copy(self):
        return copy.copy(self)

    def fill_usd_per_asset(self, usd_per_rune):
        self.usd_per_asset = usd_per_rune * self.runes_per_asset

    @property
    def asset_per_rune(self):
        return self.balance_asset / self.balance_rune

    @property
    def runes_per_asset(self):
        return self.balance_rune / self.balance_asset

    @property
    def usd_per_rune(self):
        return self.usd_per_asset * self.asset_per_rune if self.asset_per_rune else 0.0

    @staticmethod
    def is_status_enabled(status):
        return status.lower() in (PoolInfo.DEPRECATED_ENABLED, PoolInfo.AVAILABLE)  # v2 compatibility

    @property
    def is_enabled(self):
        return self.is_status_enabled(self.status)

    def usd_depth(self, usd_per_rune):
        pool_depth_usd = 2 * thor_to_float(self.balance_rune) * usd_per_rune  # note: * 2 as in off. frontend
        return pool_depth_usd

    def calculate_pool_units_rune_asset(self, add_rune: int, add_asset: int) -> PoolUnitsAdjustment:
        r0, a0 = self.balance_rune, self.balance_asset
        r, a = add_rune, add_asset

        if r0 + r == 0 or a0 + a == 0:
            logging.warning(f'total rune or asset is zero: {r0 + r = }, {a0 + a = }!')
            return PoolUnitsAdjustment(0, 0)
        if r0 == 0 or a0 == 0:
            return PoolUnitsAdjustment(add_rune, add_rune)

        slip_adjustment = 1.0 - abs((r0 * a - r * a0) / ((r + r0) * (a + a0)))

        delta_units = int(self.units * (a * r0 + a0 * r) / (2 * r0 * a0) * slip_adjustment)
        new_pool_unit = delta_units + self.units

        return PoolUnitsAdjustment(delta_units, new_pool_unit)

    @classmethod
    def from_dict_brief(cls, j):
        try:
            return cls(**j)
        except TypeError:
            pass

    def as_dict_brief(self):
        return dataclasses.asdict(self)

    @property
    def rune_price(self):
        return self.usd_per_asset / self.runes_per_asset

    @property
    def usd_volume_24h(self):
        """ Used for top_pools """
        return thor_to_float(self.volume_24h) * self.rune_price

    @property
    def total_liquidity(self):
        """ Used for top_pools """
        return 2.0 * thor_to_float(self.balance_rune) * self.rune_price

    def get_synth_cap_in_asset_float(self, max_synth_per_pool_depth=0.15):
        return thor_to_float(self.balance_asset * max_synth_per_pool_depth * 2.0)

    @property
    def savers_depth_float(self):
        return thor_to_float(self.savers_depth)

    @property
    def saver_growth_rune(self):
        return thor_to_float((self.savers_depth - self.savers_units) * self.runes_per_asset)

    @property
    def saver_growth(self):
        return self.savers_depth / self.savers_units if self.savers_units else 0.0

    @property
    def synth_asset_name(self):
        return self.asset.replace('.', '/')

    @property
    def synth_supply_float(self):
        return thor_to_float(self.synth_supply)

    def __post_init__(self):
        self.is_virtual = Asset(self.asset).is_virtual

    @classmethod
    def from_midgard_json(cls, j):
        return cls(
            asset=j.get('asset'),
            balance_asset=int(j.get('assetDepth', 0)),
            balance_rune=int(j.get('runeDepth', 0)),
            pool_units=int(j.get('liquidityUnits', 0)),
            status=str(j.get('status', '')).lower(),
            usd_per_asset=float(j.get('assetPriceUSD', 0.0)),
            pool_apy=float(j.get('poolAPY', 0.0)) * 100.0,
            synth_supply=int(j.get('synthSupply', 0)),
            synth_units=int(j.get('synthUnits', 0)),
            units=int(j.get('units', 0)),
            volume_24h=int(j.get('volume24h', 0)),
            savers_units=int(j.get('saversUnits', 0)),
            savers_depth=int(j.get('saversDepth', 0)),
            savers_apr=float(j.get('saversAPR', 0)),
            pool_apr=float(j.get('annualPercentageRate', 0)) * 100.0,
        )


@dataclass
class PoolInfoHistoricEntry:
    asset_depth: int = 0
    rune_depth: int = 0
    asset_price: float = 0.0
    asset_price_usd: float = 0.0
    liquidity_units: int = 0
    synth_units: int = 0
    synth_supply: int = 0
    luvi: float = 0.0
    units: int = 0
    timestamp: int = 0
    members_count: int = 0

    def to_pool_info(self, asset) -> PoolInfo:
        return PoolInfo(
            asset,
            self.asset_depth,
            self.rune_depth,
            self.liquidity_units,
            PoolInfo.DEPRECATED_ENABLED,
            units=self.liquidity_units,
            original=None,
        )

    @classmethod
    def from_json(cls, j):
        asset_depth = int(j.get('assetDepth', '0'))
        rune_depth = int(j.get('runeDepth', '0'))
        asset_price = asset_depth / rune_depth if rune_depth else 0.0
        return PoolInfoHistoricEntry(
            asset_depth=asset_depth,
            rune_depth=rune_depth,
            units=int(j.get('units', 0)),  # total liquidity units!
            synth_units=int(j.get('synthUnits', 0)),
            synth_supply=int(j.get('synthSupply', 0)),
            liquidity_units=int(j.get('liquidityUnits', 0)),
            asset_price=float(j.get('assetPrice', asset_price)),
            asset_price_usd=float(j.get('assetPriceUSD', 0.0)),
            timestamp=int(j.get('endTime', 0)),
            members_count=int(j.get('membersCount', 0)),
            luvi=float(j.get('luvi', 0)),
        )


@dataclass
class PoolDepthResponse:
    intervals: List[PoolInfoHistoricEntry]

    @classmethod
    def from_json(cls, r):
        return cls(
            intervals=[PoolInfoHistoricEntry.from_json(j) for j in r.get('intervals', [])]
        )


PoolInfoMap = Dict[str, PoolInfo]


def parse_thor_pools(thor_pools: List[ThorPool]) -> PoolInfoMap:
    """
    Converts a list of ThorPool from THORNode to PoolInfoMap
    @attention ThorPool is missing some high-level stats like APY
    @param thor_pools:
    @return:
    """
    return {
        p.asset: PoolInfo(
            p.asset,
            p.balance_asset, p.balance_rune,
            int(p.lp_units), p.status,
            synth_units=int(p.synth_units),
            units=int(p.pool_units),
            savers_depth=p.savers_depth,
            savers_units=p.savers_units,
            synth_supply=p.synth_supply,
            original=p,
            usd_per_asset=p.tor_per_asset,
        )
        for p in thor_pools
    }


class PoolChange(NamedTuple):
    pool_name: str
    old_status: str
    new_status: str


class PoolChanges(NamedTuple):
    pools_added: List[PoolChange]
    pools_removed: List[PoolChange]
    pools_changed: List[PoolChange]

    @property
    def any_changed(self):
        return self.pools_changed or self.pools_added or self.pools_removed


class EventPools(NamedTuple):
    pool_detail_dic: PoolInfoMap
    pool_detail_dic_prev: PoolInfoMap
    earnings: Optional[EarningHistoryResponse] = None
    usd_per_rune: float = 0.0

    BY_VOLUME_24h = 'usd_volume_24h'
    BY_DEPTH = 'total_liquidity'
    BY_APY = 'pool_apy'
    BY_APR = 'pool_apr'
    BY_INCOME_FULL = 'earnings'
    BY_INCOME_LIQ = 'total_liquidity_fees_rune'

    @staticmethod
    def bad_value(x: float):
        return math.isinf(x) or math.isnan(x)

    @property
    def all_assets(self):
        return set(self.pool_detail_dic.keys()) | set(self.pool_detail_dic_prev.keys())

    def get_top_pools(self, criterion: str, n=None, descending=True) -> List[PoolInfo]:
        pools = self.pool_detail_dic.values()
        criterion = str(criterion)

        if criterion in (self.BY_APR, self.BY_VOLUME_24h):
            pools = filter(lambda p: p.is_enabled, pools)
        pools = filter(lambda p: not self.bad_value(self.get_value(p.asset, criterion)), pools)

        pool_list = list(pools)
        pool_list.sort(key=lambda p: self.get_value(p.asset, criterion), reverse=descending)
        return pool_list if n is None else pool_list[:n]

    def total_value(self, attr_name, is_previous=False):
        if attr_name == EventPools.BY_DEPTH:
            return self.total_liquidity()
        elif attr_name == EventPools.BY_VOLUME_24h:
            return self.total_volume_24h()
        elif attr_name in (EventPools.BY_INCOME_FULL, EventPools.BY_INCOME_LIQ):
            scoped_intervals = self.get_earning_interval(is_previous)

            total_earnings_usd = 0.0
            for interval in scoped_intervals:
                for pool in interval.pools:
                    total_earnings_usd += thor_to_float(getattr(pool, attr_name)) * interval.rune_price_usd

            return total_earnings_usd
        return 0.0

    def get_earning_interval(self, is_previous=False):
        intervals = self.earnings.intervals
        tally_days_period = len(intervals) // 2
        scoped_intervals = intervals[0:tally_days_period] if not is_previous else intervals[tally_days_period:]
        return scoped_intervals

    def get_value(self, pool_name, attr_name, is_previous=False):
        if attr_name in (self.BY_INCOME_FULL, self.BY_INCOME_LIQ):
            scoped_intervals = self.get_earning_interval(is_previous)

            pool_earnings = 0.0
            for interval in scoped_intervals:
                # pool = next((p for p in interval.pools if p.pool == pool_name), None)
                for pool in interval.pools:
                    if (pool_name and pool.pool == pool_name) or not pool_name:
                        pool_earnings += thor_to_float(getattr(pool, attr_name)) * interval.rune_price_usd

            return pool_earnings

        source = self.pool_detail_dic if not is_previous else self.pool_detail_dic_prev
        if pool_name not in source:
            raise KeyError(f'no pool: {pool_name}')

        pool = source[pool_name]
        return float(getattr(pool, attr_name))

    @property
    def total_pool_earnings_full(self):
        return self.get_value(None, self.BY_INCOME_FULL)

    @property
    def total_pool_earnings_liq(self):
        return self.get_value(None, self.BY_INCOME_LIQ)

    def get_difference_percent(self, pool_name, attr_name):
        curr_value = self.get_value(pool_name, attr_name)
        prev_value = self.get_value(pool_name, attr_name, is_previous=True)
        if prev_value == 0.0:
            return None

        if attr_name == self.BY_APR:
            return curr_value - prev_value
        else:
            return (curr_value / prev_value - 1.0) * 100.0

    @property
    def empty(self):
        return not self.pool_detail_dic

    @property
    def number_of_active_pools(self):
        return len([pool for pool in self.pool_detail_dic.values() if pool.is_enabled])

    def total_liquidity(self, prev=False):
        scope = self.pool_detail_dic_prev if prev else self.pool_detail_dic
        return sum(p.total_liquidity for p in scope.values())

    def total_volume_24h(self, prev=False):
        scope = self.pool_detail_dic_prev if prev else self.pool_detail_dic
        return sum(p.usd_volume_24h for p in scope.values())

    @property
    def total_liquidity_diff_percent(self):
        if not self.pool_detail_dic_prev:
            return None

        prev = self.total_liquidity(prev=True)
        curr = self.total_liquidity()
        return calc_percent_change(prev, curr)

    @property
    def total_volume_24h_diff_percent(self):
        if not self.pool_detail_dic_prev:
            return None

        prev = self.total_volume_24h(prev=True)
        curr = self.total_volume_24h()
        return calc_percent_change(prev, curr)

    @property
    def pool_earnings_liq_diff_percent(self):
        if not self.pool_detail_dic_prev:
            return None

        prev = self.total_pool_earnings_liq
        curr = self.total_pool_earnings_liq
        return calc_percent_change(prev, curr)
