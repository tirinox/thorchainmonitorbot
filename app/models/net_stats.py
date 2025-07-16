from dataclasses import dataclass
from typing import Optional, NamedTuple, List

from .base import BaseModelMixin
from .node_info import NodeInfo
from .swap_history import SwapsHistoryEntry


@dataclass
class NetworkStats(BaseModelMixin):
    date_ts: int = 0

    usd_per_rune: float = 0.0  # stats

    bonding_apy: float = 0.0  # network
    liquidity_apy: float = 0.0  # network

    users_daily: int = 0  # stats
    users_monthly: int = 0  # stats

    swap_volume_rune: float = 0.0  # stats
    swaps_total: int = 0  # stats
    swaps_24h: int = 0  # stats
    swaps_30d: int = 0  # stats
    unique_swapper_count: int = 0  # stats

    switched_rune: float = 0  # stats

    add_count: int = 0  # stats
    withdraw_count: int = 0  # stats
    added_rune: float = 0  # stats
    withdrawn_rune: float = 0  # stats

    loss_protection_paid_rune: float = 0.0  # stats
    loss_protection_paid_24h_rune: float = 0.0  # ILP tracker

    active_pool_count: int = 0  # pools
    pending_pool_count: int = 0  # pools

    active_nodes: int = 0  # network
    standby_nodes: int = 0  # network

    total_rune_lp: float = 0.0  # stats
    total_rune_pol: float = 0.0  # Protocol owned liquidity
    total_rune_pool: float = 0.0  # rune pool
    total_bond_rune: float = 0.0  # network
    total_active_bond_rune: float = 0.0  # network

    reserve_rune: float = 0.0  # network

    next_pool_activation_ts: int = 0  # network
    next_pool_to_activate: str = ''  # pools

    synth_op_count: int = 0  # swap history
    synth_volume_24h: float = 0  # swap history
    trade_op_count: int = 0  # swap history
    trade_volume_24h: float = 0  # swap history

    swap_volume_24h: float = 0  # swap history

    swap_stats: Optional[SwapsHistoryEntry] = None

    @property
    def total_bond_usd(self):
        return self.total_bond_rune * self.usd_per_rune

    @property
    def total_active_bond_usd(self):
        return self.total_active_bond_rune * self.usd_per_rune

    @property
    def total_pooled_usd(self):
        return self.total_rune_lp * self.usd_per_rune

    @property
    def total_liquidity_usd(self):
        return self.total_pooled_usd * 2

    @property
    def total_locked_usd(self):
        return self.total_liquidity_usd + self.total_bond_usd

    @property
    def swap_volume_usd(self):
        return self.swap_volume_rune * self.usd_per_rune

    @property
    def swap_volume_usd_24h(self):
        return self.swap_volume_24h * self.usd_per_rune

    @property
    def loss_protection_paid_usd(self):
        return self.loss_protection_paid_rune * self.usd_per_rune

    @property
    def added_usd(self):
        return self.added_rune * self.usd_per_rune

    @property
    def withdrawn_usd(self):
        return self.withdrawn_rune * self.usd_per_rune

    @property
    def synth_volume_24h_usd(self):
        return self.synth_volume_24h * self.usd_per_rune

    @property
    def trade_volume_24h_usd(self):
        return self.trade_volume_24h * self.usd_per_rune

    @property
    def swap_volume_24h_usd(self):
        return self.swap_volume_24h * self.usd_per_rune

    @property
    def total_nodes(self):
        return self.active_nodes + self.standby_nodes

    @property
    def is_ok(self):
        return self.total_rune_lp > 0 and self.active_pool_count > 0 \
            and self.active_nodes > 0 and self.total_active_bond_rune > 0


class AlertNetworkStats(NamedTuple):
    old: NetworkStats
    new: NetworkStats
    nodes: List[NodeInfo]
