from typing import NamedTuple, List, Optional

from aiothornode.types import ThorPOL, thor_to_float

from services.models.pool_member import PoolMemberDetails
from services.models.price import LastPriceHolder


class EventPOL(NamedTuple):
    current: ThorPOL
    membership: List[PoolMemberDetails]
    previous: Optional[ThorPOL] = None
    prices: Optional[LastPriceHolder] = None
    mimir_synth_target_ptc: float = 45.0  # %
    mimir_max_deposit: float = 10_000.0  # Rune

    @property
    def usd_value(self):
        return self.prices.usd_per_rune * self.rune_value_float

    @property
    def rune_value_float(self):
        return thor_to_float(self.current.value)

    @property
    def rune_pnl_float(self):
        return thor_to_float(self.current.pnl)

    @property
    def pnl_percent(self):
        return self.current.pnl / self.current.current_deposit if self.current.current_deposit else 0.0

    @property
    def pol_utilization_percent(self):
        return self.rune_value_float / self.mimir_max_deposit * 100.0 if self.mimir_max_deposit else 0.0
