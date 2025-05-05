from jobs.scanner.block_result import BlockResult
from lib.delegates import WithDelegates, INotified
from lib.depcont import DepContainer
from lib.logs import WithLogger


class TCYTracker(WithDelegates, INotified, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

    async def on_data(self, sender, block: BlockResult):
        events = await self.get_events_from_block(block)
        for ev in events:
            await self._store_event(ev)
            await self.pass_data_to_listeners(ev)

    async def get_events_from_block(self, block):
        return []

    async def _store_event(self, ev):
        pass
