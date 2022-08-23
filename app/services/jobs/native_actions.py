from typing import List

from services.jobs.fetch.native_scan import BlockResult
from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger


class NativeActionExtractor(WithDelegates, INotified, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

    async def on_data(self, sender, txs: List[BlockResult]):
        ...
