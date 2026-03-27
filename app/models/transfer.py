from dataclasses import dataclass, field
from typing import List

from lib.constants import RUNE_DENOM
from lib.date_utils import DAY
from .asset import is_rune


@dataclass
class NativeTokenTransfer:
    from_addr: str
    to_addr: str
    block: int
    tx_hash: str
    amount: float
    usd_per_asset: float = 1.0
    is_native: bool = False
    asset: str = ''
    comment: str = ''
    memo: str = ''
    block_ts: float = 0.0  # actual block timestamp (Unix); 0 means unknown → fall back to now

    @property
    def is_synth(self):
        return self.asset != RUNE_DENOM and '/' in self.asset

    @property
    def usd_amount(self):
        return self.usd_per_asset * self.amount

    def is_from_or_to(self, address):
        return address and (address == self.from_addr or address == self.to_addr)

    @property
    def is_rune(self):
        return is_rune(self.asset)

    def rune_amount(self, usd_per_rune):
        return self.usd_amount / usd_per_rune

    NON_SEND_COMMENTS = (
        'deposit',
        'outbound',
        'solvency',
        'observedtxout',
        'observedtxin',
    )

    def is_comment_non_send(self):
        if self.comment:
            comment = self.comment.lower()
            for ignore_comment in self.NON_SEND_COMMENTS:
                # fixme issue: bond is deposit, it is ignored
                if ignore_comment in comment:
                    return True
        return False


@dataclass
class RuneCEXFlow:
    rune_cex_inflow: float
    rune_cex_outflow: float
    total_transfers: int
    overflow: bool = False
    usd_per_rune: float = 0.0
    period_sec: float = DAY

    @property
    def total_rune(self):
        return self.rune_cex_inflow + self.rune_cex_outflow

    @property
    def rune_cex_netflow(self):
        return self.rune_cex_inflow - self.rune_cex_outflow

    @property
    def in_usd(self):
        return self.usd_per_rune * self.rune_cex_inflow

    @property
    def out_usd(self):
        return self.usd_per_rune * self.rune_cex_outflow

    @property
    def netflow_usd(self):
        return self.usd_per_rune * self.rune_cex_netflow


@dataclass
class AlertRuneTransferStats:
    """Aggregated RUNE transfer statistics for an N-day window, ready for rendering."""
    period_days: int
    start_date: str
    end_date: str
    volume_rune: float
    transfer_count: int
    cex_inflow_rune: float
    cex_outflow_rune: float
    cex_inflow_count: int
    cex_outflow_count: int
    cex_netflow_rune: float        # inflow − outflow  (positive = net deposits to CEX)
    usd_per_rune: float = 0.0
    daily: List[dict] = field(default_factory=list)

    @classmethod
    def from_summary(cls, summary: dict, usd_per_rune: float = 0.0) -> 'AlertRuneTransferStats':
        return cls(
            period_days=int(summary.get('days', 0)),
            start_date=summary.get('start_date', ''),
            end_date=summary.get('end_date', ''),
            volume_rune=float(summary.get('volume_rune', 0)),
            transfer_count=int(summary.get('transfer_count', 0)),
            cex_inflow_rune=float(summary.get('cex_inflow_rune', 0)),
            cex_outflow_rune=float(summary.get('cex_outflow_rune', 0)),
            cex_inflow_count=int(summary.get('cex_inflow_count', 0)),
            cex_outflow_count=int(summary.get('cex_outflow_count', 0)),
            cex_netflow_rune=float(summary.get('cex_netflow_rune', 0)),
            usd_per_rune=usd_per_rune,
            daily=summary.get('daily', []),
        )

    def to_dict(self) -> dict:
        """Produce the variable dict expected by rune_transfer_stats.jinja2."""
        return {
            'period_days': self.period_days,
            'usd_per_rune': self.usd_per_rune,
            'total': {
                'start_date': self.start_date,
                'end_date': self.end_date,
                'volume_rune': self.volume_rune,
                'transfer_count': self.transfer_count,
                'cex_inflow_rune': self.cex_inflow_rune,
                'cex_outflow_rune': self.cex_outflow_rune,
                'cex_inflow_count': self.cex_inflow_count,
                'cex_outflow_count': self.cex_outflow_count,
                'cex_netflow_rune': self.cex_netflow_rune,
            },
            'daily': self.daily,
        }

