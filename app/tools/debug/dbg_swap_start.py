import asyncio

from jobs.fetch.stream_watchlist import StreamingSwapStartDetectorFromList, StreamingSwapWatchListFetcher
from jobs.scanner.scan_cache import BlockScannerCached
from jobs.scanner.swap_start_detector import SwapStartDetectorFromBlock
from notify.public.s_swap_notify import StreamingSwapStartTxNotifier
from tools.lib.lp_common import LpAppFramework


async def dbg_run_continuous(app: LpAppFramework):
    d = app.deps

    d.block_scanner = BlockScannerCached(d)

    swap_start_detector = SwapStartDetectorFromBlock(d)
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

    sssd = StreamingSwapStartDetectorFromList(d)
    sssd.add_subscriber(d.alert_presenter)
    ph = await d.pool_cache.get()
    # noinspection PyProtectedMember


    await sssd._handle_swap_start(s_swap, ph)

    await asyncio.sleep(5.0)


async def run():
    app = LpAppFramework()
    async with app:
        # await dbg_run_continuous(app)
        await dbg_run_specific_tx(app, '9780B3B145291DDDDE40CCFE0896D1D7A66C8E03E23EA3AC6A20F2414F66ECA7')


if __name__ == '__main__':
    asyncio.run(run())
