from typing import NamedTuple

from services.lib.constants import thor_to_float


class EventLoanOpen(NamedTuple):
    tx_id: str
    address: str
    asset: str
    amount: int
    debt_usd: float

    @property
    def amount_float(self):
        return thor_to_float(self.amount)


class EventLoanRepayment(NamedTuple):
    tx_id: str
    address: str
    asset: str
    amount: int
    debt_usd: float

    @property
    def amount_float(self):
        return thor_to_float(self.amount)
