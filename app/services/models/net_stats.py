from dataclasses import dataclass

from services.models.base import BaseModelMixin


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

    switched_rune: float = 0  # stats

    add_count: int = 0  # stats
    withdraw_count: int = 0  # stats
    added_rune: float = 0  # stats
    withdrawn_rune: float = 0  # stats

    loss_protection_paid_rune: float = 0.0  # stats

    active_pool_count: int = 0  # pools
    pending_pool_count: int = 0  # pools

    active_nodes: int = 0  # network
    standby_nodes: int = 0  # network

    # bep2_liquidity_usd: float = 0  # todo

    total_rune_pooled: float = 0.0  # stats
    total_bond_rune: float = 0.0  # network
    total_active_bond_rune: float = 0.0  # network

    reserve_rune: float = 0.0  # network

    next_pool_activation_ts: int = 0  # network
    next_pool_to_activate: str = ''  # pools

    @property
    def total_bond_usd(self):
        return self.total_bond_rune * self.usd_per_rune

    @property
    def total_pooled_usd(self):
        return self.total_rune_pooled * self.usd_per_rune

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
    def loss_protection_paid_usd(self):
        return self.loss_protection_paid_rune * self.usd_per_rune

    @property
    def added_usd(self):
        return self.added_rune * self.usd_per_rune

    @property
    def withdrawn_usd(self):
        return self.withdrawn_rune * self.usd_per_rune

    @property
    def network_security_ratio(self):
        divisor = self.total_active_bond_rune + self.total_rune_pooled
        return self.total_active_bond_rune / divisor if divisor else 0.0

    @property
    def total_nodes(self):
        return self.active_nodes + self.standby_nodes

    @property
    def is_ok(self):
        return self.total_rune_pooled > 0 and self.active_pool_count > 0 and \
               self.total_bond_rune > 0 and self.active_nodes > 0
