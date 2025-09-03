from dataclasses import dataclass

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
