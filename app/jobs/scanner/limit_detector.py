from jobs.scanner.block_result import BlockResult
from lib.delegates import INotified, WithDelegates
from lib.depcont import DepContainer
from lib.logs import WithLogger


class LimitSwapDetector(WithLogger, INotified, WithDelegates):
    REASON_EXPIRED = "limit swap expired"
    REASON_COMPLETED = "swap has been completed."
    REASON_CANCELLED = "limit swap cancelled"
    REASON_MARKET = "market swap completed"
    REASON_FAILED = "limit swap failed"

    @staticmethod
    def is_completed(status):
        return "completed" in status.lower()

    @staticmethod
    def get_closed_limit_swaps(block: BlockResult):
        # search for "limit_swap_close" EndBlock event
        for e in block.end_block_events:
            if e.type == 'limit_swap_close':
                yield e.attrs.get('txid'), e.attrs.get('reason')

    async def on_data(self, sender, b: BlockResult):
        pass

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
