import dataclasses
import operator
from collections import defaultdict
from datetime import datetime
from functools import cached_property
from typing import NamedTuple, List, Tuple, Optional

from lib.constants import STABLE_COIN_POOLS_ALL, thor_to_float
from .affiliate import AffiliateCollector
from .earnings_history import EarningsTuple
from .pool_info import PoolInfoMap
from .swap_history import SwapHistoryResponse


class SwapRouteEntry(NamedTuple):
    from_asset: str
    to_asset: str
    volume_rune: float


class LockedValue(NamedTuple):
    date: datetime
    total_value_pooled: float = 0.0
    total_value_pooled_usd: float = 0.0
    total_value_bonded: float = 0.0
    total_value_bonded_usd: float = 0.0
    total_value_locked: float = 0.0
    total_value_locked_usd: float = 0.0

    @property
    def total_non_rune_usd(self):
        return self.total_value_pooled_usd * 0.5


@dataclasses.dataclass
class KeyStats:
    pools: PoolInfoMap
    lock: LockedValue
    swap_vol: dict
    swap_count: dict
    swapper_count: int

    earnings: EarningsTuple


@dataclasses.dataclass
class AlertKeyStats:
    start_date: datetime
    end_date: datetime
    current: KeyStats  # compound
    previous: KeyStats  # compound
    routes: List[SwapRouteEntry]  # recorded
    swap_type_distribution: dict  # recorded
    top_affiliates: List[AffiliateCollector]
    days: int = 7

    mdg_swap_stats: Optional[SwapHistoryResponse] = None

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
    def swap_routes(self):
        collectors = defaultdict(float)
        for obj in self.routes:
            collectors[(obj.from_asset, obj.to_asset)] += obj.volume_rune
        return list(sorted(collectors.items(), key=operator.itemgetter(1), reverse=True))

    @cached_property
    def usd_volume_curr_prev(self) -> Tuple[float, float]:
        curr, prev = self.mdg_swap_stats.curr_and_prev_interval("total_volume_usd")
        return curr, prev

    @property
    def locked_value_usd_curr_prev(self):
        return self.current.lock.total_value_locked_usd, self.previous.lock.total_value_locked_usd
