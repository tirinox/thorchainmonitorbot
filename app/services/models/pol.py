from typing import NamedTuple, List, Optional

from aiothornode.types import ThorPOL, thor_to_float

from services.models.pool_member import PoolMemberDetails
from services.models.price import LastPriceHolder


class POLState(NamedTuple):
    usd_per_rune: float
    value: ThorPOL

    @property
    def rune_value(self):
        return thor_to_float(self.value.value)

    @property
    def rune_deposited(self):
        return thor_to_float(self.value.rune_deposited)

    @property
    def rune_withdrawn(self):
        return thor_to_float(self.value.rune_withdrawn)

    @property
    def usd_value(self):
        return self.usd_per_rune * self.rune_value

    def pol_utilization_percent(self, mimir_max_deposit):
        return self.rune_value / mimir_max_deposit * 100.0 if mimir_max_deposit else 0.0

    @property
    def pnl_percent(self):
        return self.value.pnl / self.value.current_deposit if self.value.current_deposit else 0.0


class EventPOL(NamedTuple):
    current: POLState
    membership: List[PoolMemberDetails]
    previous: Optional[POLState] = None
    prices: Optional[LastPriceHolder] = None
    mimir_synth_target_ptc: float = 45.0  # %
    mimir_max_deposit: float = 10_000.0  # Rune

    @property
    def pol_utilization(self):
        return self.current.pol_utilization_percent(self.mimir_max_deposit)
