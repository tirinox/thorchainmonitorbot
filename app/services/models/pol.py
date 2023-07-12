import dataclasses
from typing import NamedTuple, List, Optional

from aiothornode.types import ThorPOL, thor_to_float

from services.models.pool_member import PoolMemberDetails
from services.models.price import LastPriceHolder


class POLState(NamedTuple):
    usd_per_rune: float
    value: ThorPOL

    @property
    def is_zero(self):
        if not self.value:
            return True

        return (not self.value.value or self.rune_value == 0) and \
            (self.rune_deposited == 0 and self.rune_withdrawn == 0)

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

    @classmethod
    def load_from_series(cls, j):
        usd_per_rune = float(j.get('usd_per_rune', 1.0))
        pol = POLState(usd_per_rune, ThorPOL(**j.get('pol')))
        membership = [PoolMemberDetails(**it) for it in j.get('membership', [])]
        return cls(
            current=pol,
            membership=membership,
        )

    @property
    def to_json_for_series(self):
        return {
            'pol': self.current.value._asdict(),
            'membership': [
                dataclasses.asdict(m) for m in self.membership
            ],
            'usd_per_rune': self.current.usd_per_rune,
        }
