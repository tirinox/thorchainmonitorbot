import dataclasses
import operator
from collections import defaultdict
from datetime import datetime
from functools import cached_property
from typing import NamedTuple, List, Tuple, Optional

from lib.constants import STABLE_COIN_POOLS_ALL, thor_to_float
from lib.date_utils import date_parse_rfc_z_no_ms
from models.pool_info import PoolInfoMap
from models.swap_history import SwapHistoryResponse


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


class AffiliateCollectors(NamedTuple):
    date: datetime
    label: str
    fee_usd: float = 0.0
    cumulative_fee_usd: float = 0.0
    total_cumulative_fee_usd: float = 0.0

    @staticmethod
    def parse_date(d):
        try:
            return date_parse_rfc_z_no_ms(d)
        except ValueError:
            try:
                return datetime.strptime(d, '%Y-%m-%d') if d else None
            except ValueError:
                return datetime.strptime(d, '%Y-%m-%d %H:%M:%S.%f')

    @classmethod
    def from_json(cls, j):
        return cls(
            cls.parse_date(j.get('DAY')),
            j.get('LABEL', ''),
            fee_usd=float(j.get('FEE_USD', 0.0)),
            cumulative_fee_usd=float(j.get('CUMULATIVE_FEE_USD', 0.0)),
            total_cumulative_fee_usd=float(j.get('TOTAL_CUMULATIVE_FEE_USD', 0.0)),
        )


@dataclasses.dataclass
class KeyStats:
    pools: PoolInfoMap
    lock: LockedValue
    swap_vol: dict
    swap_count: dict
    swapper_count: int
    protocol_revenue_usd: float
    affiliate_revenue_usd: float
    block_rewards_usd: float
    fee_rewards_usd: float


@dataclasses.dataclass
class AlertKeyStats:
    start_date: datetime
    end_date: datetime
    current: KeyStats  # compound
    previous: KeyStats  # compound
    routes: List[SwapRouteEntry]  # recorded
    swap_type_distribution: dict  # recorded
    top_affiliates_usd: dict[str, float]
    days: int = 7

    runepool_depth: float = 0.0  # from thornode
    runepool_prev_depth: float = 0.0  # from thornode

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
    def top_affiliate_daily(self):
        collectors = self.top_affiliates_usd
        return list(sorted(collectors.items(), key=operator.itemgetter(1), reverse=True))

    @property
    def swap_routes(self):
        collectors = defaultdict(float)
        for obj in self.routes:
            collectors[(obj.from_asset, obj.to_asset)] += obj.volume_rune
        return list(sorted(collectors.items(), key=operator.itemgetter(1), reverse=True))

    @cached_property
    def block_ratio(self):
        block_rewards_usd = self.current.block_rewards_usd
        total_revenue_usd = self.current.protocol_revenue_usd
        block_ratio_v = block_rewards_usd / total_revenue_usd if total_revenue_usd else 100.0
        return block_ratio_v

    @cached_property
    def organic_ratio(self):
        return self.current.fee_rewards_usd / self.current.protocol_revenue_usd \
            if self.current.protocol_revenue_usd else 100.0

    @cached_property
    def usd_volume_curr_prev(self) -> Tuple[float, float]:
        # return self.current.swap_vol.get(TxMetricType.SWAP, 0), self.previous.swap_vol.get(TxMetricType.SWAP, 0)
        interval_curr, interval_prev = self.mdg_swap_stats.curr_and_prev_interval()
        return (
            interval_curr.rune_price_usd * thor_to_float(interval_curr.total_volume),
            interval_prev.rune_price_usd * thor_to_float(interval_prev.total_volume)
        )

    @property
    def locked_value_usd_curr_prev(self):
        return self.current.lock, self.previous.lock
