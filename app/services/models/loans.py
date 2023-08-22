from typing import NamedTuple

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
