from services.jobs.scanner.event_db import EventDatabase
from services.jobs.scanner.native_scan import BlockResult
from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger


class LoanTxNotifier(INotified, WithDelegates, WithLogger):
    def __init__(self, deps: DepContainer, prefix='thor'):
        super().__init__()
        self.deps = deps
        self.prefix = prefix
        self._ev_db = EventDatabase(deps.db)
        self.min_volume_usd = self.deps.cfg.as_float('tx.loans.min_usd_total', 2500.0)
        self.curve_mult = self.deps.cfg.as_float('tx.loans.curve_mult', 1.0)

    async def on_data(self, sender, data: BlockResult):
        pass
        # await self.pass_data_to_listeners(...)
