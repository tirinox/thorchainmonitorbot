from _operator import attrgetter
from dataclasses import dataclass
from typing import List, NamedTuple, Optional

from services.lib.constants import BLOCKS_PER_YEAR, SAVERS_BEGIN_BLOCK, thor_to_float
from services.models.pool_info import PoolInfoMap, PoolInfo
from services.models.price import LastPriceHolder

TYPICAL_REBALANCE_RATIO = 0.5


@dataclass
class SaverVault:
    asset: str
    number_of_savers: int
    total_asset_saved: float
    total_asset_saved_usd: float
    apr: float
    asset_cap: float
    runes_earned: float
    synth_supply: float

    @property
    def percent_of_cap_filled(self):
        return self.synth_supply / self.asset_cap * 100.0 if self.asset_cap else 0.0

    @property
    def usd_per_asset(self):
        return self.total_asset_saved_usd / self.total_asset_saved

    def calc_asset_earned(self, pool_map: PoolInfoMap):
        if pool_map and (pool := pool_map.get(self.asset)):
            return pool.asset_per_rune * self.runes_earned
        else:
            return 0.0

    @staticmethod
    def calc_total_saved_usd(asset, total_asset_saved, pool_map: PoolInfoMap):
        if pool_map and (pool := pool_map.get(asset)):
            price = pool.usd_per_asset
            result = total_asset_saved * price if price else 0.0
        else:
            result = 0.0
        return result


@dataclass
class AllSavers:
    total_unique_savers: int
    vaults: List[SaverVault]

    def fill_total_usd(self, pool_map: PoolInfoMap):
        for v in self.vaults:
            v.total_asset_saved_usd = v.calc_total_saved_usd(v.asset, v.total_asset_saved, pool_map)

    @property
    def total_usd_saved(self) -> float:
        return sum(s.total_asset_saved_usd for s in self.vaults)

    @property
    def apr_list(self):
        return [s.apr for s in self.vaults]

    @property
    def average_apr(self) -> float:
        if not self.vaults:
            return 0.0
        return sum(self.apr_list) / len(self.vaults)

    @property
    def min_apr(self):
        return min(self.apr_list)

    @property
    def max_apr(self):
        return max(self.apr_list)

    def sort_vaults(self, key='apr', reverse=False):
        self.vaults.sort(key=attrgetter(key), reverse=reverse)
        return self

    def get_top_vaults(self, criterion: str, n=None, descending=True) -> List[SaverVault]:
        vault_list = list(self.vaults)
        vault_list.sort(key=attrgetter(criterion), reverse=descending)
        return vault_list if n is None else vault_list[:n]

    @property
    def total_rune_earned(self):
        return sum(p.runes_earned for p in self.vaults)

    def calculate_synth_minted_usd(self, pool_map: PoolInfoMap):
        accum = 0.0
        for vault in self.vaults:
            pool = pool_map.get(vault.asset)
            if pool:
                accum += pool.synth_supply_float * pool.usd_per_asset
        return accum

    def calculate_synth_possible_usd(self, pool_map: PoolInfoMap):
        accum = 0.0
        for vault in self.vaults:
            pool = pool_map.get(vault.asset)
            if pool:
                accum += vault.asset_cap * pool.usd_per_asset
        return accum

    def overall_fill_cap_percent(self, pool_map: PoolInfoMap):
        synth_minted_usd = self.calculate_synth_minted_usd(pool_map)
        synth_possible_usd = self.calculate_synth_possible_usd(pool_map)
        return synth_minted_usd / synth_possible_usd * 100.0 if synth_possible_usd else 0.0


def get_savers_apr(pool: PoolInfo, block_no, blocks_per_year=BLOCKS_PER_YEAR) -> float:
    if not pool.savers_units:
        return 0.0
    saver_growth = (pool.savers_depth - pool.savers_units) / pool.savers_depth
    return (saver_growth / (block_no - SAVERS_BEGIN_BLOCK)) * blocks_per_year


def how_much_savings_you_can_add(pool: PoolInfo, max_synth_per_pool_depth=0.15,
                                 rebalance_ratio=TYPICAL_REBALANCE_RATIO):
    m = max_synth_per_pool_depth * 2.0
    x = (pool.balance_asset * m - pool.synth_supply) / (1.0 - rebalance_ratio * m)
    return max(0.0, thor_to_float(x))


class EventSaverStats(NamedTuple):
    previous_stats: Optional[AllSavers]
    current_stats: AllSavers
    price_holder: LastPriceHolder
