from typing import Optional, Union, List

from jobs.scanner.event_db import EventDatabase
from lib.delegates import INotified, WithDelegates
from lib.depcont import DepContainer
from lib.money import DepthCurve
from lib.utils import WithLogger, hash_of_string_repr
from models.loans import AlertLoanRepayment, AlertLoanOpen
from notify.dup_stop import TxDeduplicator


class LoanTxNotifier(INotified, WithDelegates, WithLogger):
    def __init__(self, deps: DepContainer, prefix='thor', curve: Optional[DepthCurve] = None):
        super().__init__()
        self.deps = deps
        self.prefix = prefix

        self._ev_db = EventDatabase(deps.db)
        self.min_volume_usd = self.deps.cfg.as_float('tx.loans.min_usd_total', 2500.0)

        # todo: use this curve to evaluate min threshold across all pools involved
        self.curve_mult = self.deps.cfg.as_float('tx.loans.curve_mult', 1.0)
        self.curve = curve

        self.deduplicator = TxDeduplicator(deps.db, "loans:announced-hashes")

    async def on_data(self, sender, events: List[Union[AlertLoanOpen, AlertLoanRepayment]]):
        for loan_ev in events:
            if loan_ev.collateral_usd > self.min_volume_usd:
                virt_tx_id = hash_of_string_repr(loan_ev)
                if not await self.deduplicator.have_ever_seen_hash(virt_tx_id):
                    await self.deduplicator.mark_as_seen(virt_tx_id)
                    await self.pass_data_to_listeners(loan_ev)
