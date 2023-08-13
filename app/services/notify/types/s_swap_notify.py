from services.jobs.fetch.native_scan import BlockResult
from services.lib.constants import thor_to_float, NATIVE_RUNE_SYMBOL
from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer
from services.models.s_swap import EventStreamingSwapStart, StreamingSwap


class StreamingSwapStartTxNotifier(INotified, WithDelegates):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

    def detect_streaming_swaps(self, b: BlockResult):
        ss = []

        ss.append(
            EventStreamingSwapStart(
                StreamingSwap(
                    '75327336C1EC3FE39D1DECB06C5F05756FAA5C28E0ACC777239F98D7F2903589',
                    9,
                    99,
                    0,
                    12000000,
                    139524325459200,
                    0, 0, 0, [], []
                ),
                from_address='thor1wy9cc324e7pv26ld78yjjpdh7x4k6ajvqpz0jz',
                in_amount=thor_to_float(21165040347615),
                in_asset=NATIVE_RUNE_SYMBOL,
                out_asset='ETH.THOR',
                expected_rate=thor_to_float(139524325459200),
                volume_usd=211_000 * 1.35
            )
        )

        return ss

    async def on_data(self, sender, data: BlockResult):
        swaps = self.detect_streaming_swaps(data)
        for swap_start_ev in swaps:
            await self.pass_data_to_listeners(swap_start_ev)
