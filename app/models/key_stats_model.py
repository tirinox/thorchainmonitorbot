import dataclasses
from datetime import datetime
from typing import NamedTuple, List

from .affiliate import AffiliateCollector
from .earnings_history import EarningsTuple


class SwapRouteEntry(NamedTuple):
    from_asset: str
    to_asset: str
    volume_rune: float
    volume_usd: float


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
    lock: LockedValue
    swap_vol: dict
    swap_count: dict
    swapper_count: int

    earnings: EarningsTuple

    total_volume_usd: float = 0.0

    btc_total_amount: float = 0.0
    btc_total_usd: float = 0.0
    eth_total_amount: float = 0.0
    eth_total_usd: float = 0.0
    usd_total_amount: float = 0.0


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

    @property
    def locked_value_usd_curr_prev(self):
        return self.current.lock.total_value_locked_usd, self.previous.lock.total_value_locked_usd
