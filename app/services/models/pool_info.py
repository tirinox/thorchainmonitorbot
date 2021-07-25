import copy
import logging
from dataclasses import dataclass
from typing import List, Dict, NamedTuple

from aiothornode.types import ThorPool

from services.lib.constants import thor_to_float


def pool_share(rune_depth, asset_depth, my_units, pool_total_units):
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

    DEPRECATED_BOOTSTRAP = 'bootstrap'
    DEPRECATED_ENABLED = 'enabled'
    AVAILABLE = 'available'  # enabled
    STAGED = 'staged'  # bootstrap

    def percent_share(self, runes, correction=0.0):
        full_balance_rune = 2 * thor_to_float(self.balance_rune) + correction
        return runes / full_balance_rune * 100.0

    def get_share_rune_and_asset(self, units: int) -> (float, float):
        r, a = pool_share(self.balance_rune, self.balance_asset, my_units=units, pool_total_units=self.pool_units)
        return thor_to_float(r), thor_to_float(a)

    def total_my_capital_of_pool_in_rune(self, units: int) -> float:
        r, _ = self.get_share_rune_and_asset(units)
        return r * 2.0

    @classmethod
    def dummy(cls):
        return cls('', 1, 1, 1, cls.DEPRECATED_BOOTSTRAP)

    def copy(self):
        return copy.copy(self)

    @property
    def asset_per_rune(self):
        return self.balance_asset / self.balance_rune

    @property
    def runes_per_asset(self):
        return self.balance_rune / self.balance_asset

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

        delta_units = int(self.pool_units * (a * r0 + a0 * r) / (2 * r0 * a0) * slip_adjustment)
        new_pool_unit = delta_units + self.pool_units

        return PoolUnitsAdjustment(delta_units, new_pool_unit)

    @classmethod
    def from_dict(cls, j):
        balance_asset = int(j['balance_asset'])
        balance_rune = int(j['balance_rune'])
        return cls(asset=j['asset'],
                   balance_asset=balance_asset,
                   balance_rune=balance_rune,
                   pool_units=int(j['pool_units']),
                   status=str(j['status']).lower())

    def as_dict(self):
        return {
            'balance_asset': str(self.balance_asset),
            'balance_rune': str(self.balance_rune),
            'pool_units': str(self.pool_units),
            'asset': self.asset,
            'status': self.status
        }


@dataclass
class LPPosition:
    pool: str
    liquidity_units: int
    liquidity_total: int
    rune_balance: float
    asset_balance: float
    usd_per_rune: float
    usd_per_asset: float
    total_usd_balance: float

    @classmethod
    def create(cls, pool: PoolInfo, my_units: int, usd_per_rune: float):
        usd_per_asset = usd_per_rune / pool.asset_per_rune
        return cls(
            pool=pool.asset,
            liquidity_units=my_units,
            liquidity_total=pool.pool_units,
            rune_balance=thor_to_float(pool.balance_rune),
            asset_balance=thor_to_float(pool.balance_asset),
            usd_per_rune=usd_per_rune,
            usd_per_asset=usd_per_asset,
            total_usd_balance=thor_to_float(pool.balance_rune) * usd_per_rune * 2.0
        )


@dataclass
class PoolInfoHistoricEntry:
    asset_depth: int = 0
    rune_depth: int = 0
    asset_price: float = 0.0
    asset_price_usd: float = 0.0
    liquidity_units: int = 0
    timestamp: int = 0

    def to_pool_info(self, asset) -> PoolInfo:
        return PoolInfo(
            asset,
            self.asset_depth,
            self.rune_depth,
            self.liquidity_units,
            PoolInfo.DEPRECATED_ENABLED
        )


PoolInfoMap = Dict[str, PoolInfo]


def parse_thor_pools(thor_pools: List[ThorPool]) -> PoolInfoMap:
    return {
        p.asset: PoolInfo(p.asset,
                          p.balance_asset_int, p.balance_rune_int,
                          p.pool_units_int, p.status)
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
