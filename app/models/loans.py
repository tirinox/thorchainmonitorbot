from typing import NamedTuple, Optional, List

from lib.constants import thor_to_float, THOR_BLOCK_TIME
from lib.date_utils import now_ts
from .events import EventLoanOpen, EventLoanRepayment


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
    is_enabled: bool

    @classmethod
    def from_json(cls, data: dict, is_enabled=True):
        return cls(
            debt=thor_to_float(data['debt']),
            borrowers_count=int(data['borrowersCount']),
            collateral=thor_to_float(data['collateral']),
            pool=data['pool'],
            available_rune=thor_to_float(data['availableRune']),
            fill=float(data['fill']),
            collateral_pool_in_rune=thor_to_float(data['collateralPoolInRune']),
            debt_in_rune=thor_to_float(data['debtInRune']),
            collateral_available=thor_to_float(data['collateralAvailable']),
            is_enabled=is_enabled,
        )

    @property
    def cr(self):
        # collaterization ratio
        return self.collateral_pool_in_rune / self.debt_in_rune

    @property
    def ltv(self):
        # loan-to-value
        return self.debt_in_rune / self.collateral_pool_in_rune


class LendingStats(NamedTuple):
    lending_tx_count: int
    rune_burned_rune: float
    timestamp_day: float
    usd_per_rune: float

    pools: List[BorrowerPool]

    is_paused: bool
    loan_repayment_maturity_blk: int
    min_cr: float
    max_cr: float
    lending_lever: float
    # totalAvailableRuneForProtocol = lending_lever / 10,000 * runeBurnt
    #   where runeBurnt = maxRuneSupply − currentRuneSupply

    @property
    def loan_repayment_maturity_sec(self):
        return self.loan_repayment_maturity_blk * THOR_BLOCK_TIME

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

    @property
    def avg_cr(self):
        return sum(p.cr for p in self.pools) / len(self.pools) if self.pools else 0

    @property
    def health_factor(self):
        # total burned rune / total collateral in rune
        return self.rune_burned_rune / sum(p.collateral_pool_in_rune for p in self.pools) if self.pools else 0


class AlertLendingStats(NamedTuple):
    current: LendingStats
    previous: Optional[LendingStats]


class AlertLendingOpenUpdate(NamedTuple):
    asset: str
    stats: LendingStats

    @property
    def pool_state(self) -> BorrowerPool:
        return next((p for p in self.stats.pools if p.pool == self.asset), None)
