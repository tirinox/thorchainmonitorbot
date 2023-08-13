from services.jobs.fetch.native_scan import BlockResult
from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer


class StreamingSwapStartTxNotifier(INotified, WithDelegates):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

    async def on_data(self, sender, data: BlockResult):
        pass
