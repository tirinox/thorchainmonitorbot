import asyncio
import random

from jobs.scanner.scan_cache import BlockScannerCached
from lib.texts import sep
from lib.utils import safe_get
from models.s_swap import StreamingSwap
from notify.public.s_swap_notify import StreamingSwapStartTxNotifier
from tools.lib.lp_common import LpAppFramework


async def pick_random_ongoing_streaming_swap(app: LpAppFramework):
    s_swaps = await app.deps.thor_connector.query_raw('/thorchain/swaps/streaming')
    s_swaps = [StreamingSwap.from_json(ss) for ss in s_swaps]
    if not s_swaps:
        raise RuntimeError("There is no ongoing streaming swaps!")

    print(f'{len(s_swaps) = }')
    s_swap = random.choice(s_swaps)
    print(s_swap)
    return s_swap


async def dbg_steaming_swap_start_pipeline(app: LpAppFramework):
    d = app.deps
    last_block = await d.last_block_cache.get_thor_block()
    d.block_scanner = BlockScannerCached(d, last_block=last_block - 1000)

    stream_swap_notifier = StreamingSwapStartTxNotifier(d)
    d.block_scanner.add_subscriber(stream_swap_notifier)
    stream_swap_notifier.add_subscriber(d.alert_presenter)

    await d.block_scanner.run()


async def dbg_quote(app: LpAppFramework):
    s_swap: StreamingSwap = await pick_random_ongoing_streaming_swap(app)
    tx_id = s_swap.tx_id
    tx = await app.deps.thor_connector.query_tx_details(tx_id)

    coin_in = safe_get(tx, 'tx', 'tx', 'coins', 0)

    print(tx)
    sep()
    print(coin_in)

    quote = await app.deps.thor_connector.query_swap_quote(
        from_asset=coin_in['asset'],
        to_asset='BTC.BTC',
        amount=coin_in['amount'],
        # refund_address=event.from_address,
        streaming_quantity=s_swap.quantity,
        streaming_interval=s_swap.interval,
        tolerance_bps=10000,  # MAX
        # affiliate='t' if event.memo.affiliates else '',  # does not matter for quote
        affiliate_bps=0,
        height=s_swap.last_height,  # for historical quotes
    )
    sep()
    print(quote)


async def run():
    app = LpAppFramework()
    async with app():
        # await dbg_quote(app)
        await dbg_steaming_swap_start_pipeline(app)


if __name__ == '__main__':
    asyncio.run(run())
