import asyncio

from jobs.fetch.stream_watchlist import StreamingSwapStartDetector, StreamingSwapWatchListFetcher
from jobs.scanner.scan_cache import BlockScannerCached
from jobs.scanner.swap_start_detector import SwapStartDetectorChained
from notify.public.s_swap_notify import StreamingSwapStartTxNotifier
from tools.lib.lp_common import LpAppFramework


async def dbg_run_continuous(app: LpAppFramework):
    d = app.deps

    d.block_scanner = BlockScannerCached(d)

    swap_start_detector = SwapStartDetectorChained(d)
    d.block_scanner.add_subscriber(swap_start_detector)

    stream_swap_notifier = StreamingSwapStartTxNotifier(d)
    swap_start_detector.add_subscriber(stream_swap_notifier)
    stream_swap_notifier.add_subscriber(d.alert_presenter)

    await d.block_scanner.run()
    await asyncio.sleep(5.0)


async def dbg_run_specific_tx(app: LpAppFramework, tx_id: str):
    d = app.deps

    watchlist = StreamingSwapWatchListFetcher(d)
    s_swap = await watchlist.load_streaming_swap_details(tx_id)

    sssd = StreamingSwapStartDetector(d)
    sssd.add_subscriber(d.alert_presenter)
    ph = await d.pool_cache.get()
    # noinspection PyProtectedMember


    await sssd._handle_swap_start(s_swap, ph)

    await asyncio.sleep(5.0)


async def run():
    app = LpAppFramework()
    async with app:
        # await dbg_run_continuous(app, start_block=-300)
        # await dbg_run_continuous(app)
        await dbg_run_specific_tx(app, '8BC553B659B7E474A900AE61E73D2530B554CF43C8BBF439C42F29A4E9E798AA')


if __name__ == '__main__':
    asyncio.run(run())
