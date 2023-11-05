import datetime
from datetime import date
from typing import NamedTuple

from services.jobs.fetch.flipside import FSList
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


class LendingStats(NamedTuple):
    borrower_count: int
    lending_tx_count: int
    total_collateral_value_usd: float
    total_borrowed_amount_usd: float
    rune_burned_rune: float
    btc_current_cr: float
    eth_current_cr: float
    btc_current_ltv: float
    eth_current_ltv: float
    day: date

    @classmethod
    def from_fs_json(cls, j):
        j = j[0]
        return cls(
            borrower_count=j['Borrower Count'],
            lending_tx_count=j['Lending TX Count'],
            total_collateral_value_usd=j['Total Collateral Value (USD)'],
            total_borrowed_amount_usd=j['Total Borrowed Amount (USD)'],
            rune_burned_rune=j['RUNE Burned [RUNE]'],
            btc_current_cr=j['BTC_CURRENT_CR'],
            eth_current_cr=j['ETH_CURRENT_CR'],
            btc_current_ltv=j['BTC_CURRENT_LTV'],
            eth_current_ltv=j['ETH_CURRENT_LTV'],
            day=FSList.parse_date(j['DAY'])
        )

    @property
    def data_age(self) -> float:
        return now_ts() - datetime.datetime(self.day.year, self.day.month, self.day.day).timestamp()
