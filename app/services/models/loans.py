from typing import NamedTuple, Optional, List

from services.lib.constants import thor_to_float
from services.lib.date_utils import now_ts
from services.models.events import EventLoanOpen, EventLoanRepayment


class AlertLoanOpen(NamedTuple):
    tx_id: str
    loan: EventLoanOpen
    target_price_usd: float
    collateral_price_usd: float

    @property
    def collateral_usd(self):
        return self.loan.collateral_float * self.collateral_price_usd


class AlertLoanRepayment(NamedTuple):
    tx_id: str
    loan: EventLoanRepayment
    collateral_price_usd: float

    @property
    def collateral_usd(self):
        return self.loan.collateral_float * self.collateral_price_usd


class BorrowerPool(NamedTuple):
    # from https://vanaheimex.com/api/borrowers
    debt: float
    borrowers_count: int
    collateral: float
    pool: str
    available_rune: float
    fill: float
    collateral_pool_in_rune: float
    debt_in_rune: float
    collateral_available: float

    @classmethod
    def from_json(cls, data: dict):
        return cls(
            debt=thor_to_float(data['debt']),
            borrowers_count=int(data['borrowersCount']),
            collateral=thor_to_float(data['collateral']),
            pool=data['pool'],
            available_rune=thor_to_float(data['availableRune']),
            fill=float(data['fill']),
            collateral_pool_in_rune=thor_to_float(data['collateralPoolInRune']),
            debt_in_rune=thor_to_float(data['debtInRune']),
            collateral_available=thor_to_float(data['collateralAvailable'])
        )

    @property
    def cr(self):
        # todo
        return 0.0

    @property
    def ltv(self):
        # todo
        return 0.0


class LendingStats(NamedTuple):
    lending_tx_count: int
    rune_burned_rune: float
    timestamp_day: float
    usd_per_rune: float

    pools: List[BorrowerPool]

    @property
    def total_debt(self) -> float:
        return sum(p.debt for p in self.pools)

    @property
    def borrower_count(self) -> int:
        return sum(p.borrowers_count for p in self.pools)

    @property
    def data_age(self) -> float:
        return now_ts() - self.timestamp_day

    @property
    def total_collateral_value_usd(self) -> float:
        return sum(p.collateral_pool_in_rune * self.usd_per_rune for p in self.pools)

    @property
    def total_borrowed_amount_usd(self) -> float:
        return sum(p.debt_in_rune * self.usd_per_rune for p in self.pools)


class AlertLendingStats(NamedTuple):
    current: LendingStats
    previous: Optional[LendingStats]


class AlertLendingOpenUpdate(NamedTuple):
    asset: str
    stats: LendingStats

    @property
    def pool_state(self) -> BorrowerPool:
        return next((p for p in self.stats.pools if p.pool == self.asset), None)
