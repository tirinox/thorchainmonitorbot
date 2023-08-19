from services.jobs.scanner.event_db import EventDatabase
from services.jobs.scanner.native_scan import BlockResult
from services.jobs.scanner.swap_start_detector import SwapStartDetector
from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger


class StreamingSwapStartTxNotifier(INotified, WithDelegates, WithLogger):
    def __init__(self, deps: DepContainer, prefix='thor'):
        super().__init__()
        self.deps = deps
        self.prefix = prefix
        self.detector = SwapStartDetector(deps)
        self._ev_db = EventDatabase(deps.db)

    async def on_data(self, sender, data: BlockResult):
        swaps = self.detector.detect_swaps(data)
        for swap_start_ev in swaps:
            if swap_start_ev.is_streaming:
                if not await self._ev_db.is_announced_as_started(tx_id := swap_start_ev.tx_id):
                    await self.pass_data_to_listeners(swap_start_ev)
                    await self._ev_db.announce_tx_started(tx_id)
