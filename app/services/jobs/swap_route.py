from typing import List

from services.lib.delegates import WithDelegates, INotified
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger
from services.models.time_series import TimeSeries
from services.models.tx import ThorTx, ThorTxType


class SwapRouteRecorder(WithLogger, INotified, WithDelegates):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.series = TimeSeries('SwapRoute', deps.db)

    async def on_data(self, sender, txs: List[ThorTx]):
        for tx in txs:
            if tx.type == ThorTxType.TYPE_SWAP:
                ...

        await self.pass_data_to_listeners(txs, sender)  # pass through
