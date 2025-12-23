import asyncio

from jobs.fetch.stream_watchlist import StreamingSwapWatchListFetcher, StreamingSwapStartDetector, \
    StreamingSwapStatusChecker
from lib.delegates import INotified
from models.s_swap import EventChangedStreamingSwapList, StreamingSwap
from notify.public.s_swap_notify import StreamingSwapStartTxNotifier
from tools.lib.lp_common import LpAppFramework


async def dbg_tests_parts_watchlist(app: LpAppFramework):
    swl = StreamingSwapWatchListFetcher(app.deps)

    class Receiver(INotified):
        async def on_data(self, sender, data: EventChangedStreamingSwapList):
            for s in data.new_swaps:
                s: StreamingSwap
                print(f'New streaming swap detected: {s.tx_id} ({s.source_asset} -> {s.target_asset})')
            for s in data.completed_swaps:
                s: StreamingSwap
                print(f'Streaming swap completed: {s.tx_id} ({s.source_asset} -> {s.target_asset})')

    swl.add_subscriber(Receiver())

    await swl.run()


async def dbg_run_track_of_completed_swaps(app: LpAppFramework):
    d = app.deps

    swl = StreamingSwapWatchListFetcher(d)

    checker = StreamingSwapStatusChecker(d)
    swl.add_subscriber(checker)

    class Receiver(INotified):
        async def on_data(self, sender, data):
            tx_id, details = data
            print(f'Streaming swap completed on-chain: {tx_id}')

    checker.add_subscriber(Receiver())


async def dbg_run_watchlist(app: LpAppFramework):
    d = app.deps

    # ph = await d.pool_cache.get()
    # price = ph.get_asset_price_in_usd('eth-wbtc')
    # print(f'BTC price is ${price:.2f}')

    swl = StreamingSwapWatchListFetcher(d)

    start_detector = StreamingSwapStartDetector(d)
    swl.add_subscriber(start_detector)

    stream_swap_notifier = StreamingSwapStartTxNotifier(d)
    stream_swap_notifier.hide_arb_bots = False
    start_detector.add_subscriber(stream_swap_notifier)
    stream_swap_notifier.add_subscriber(d.alert_presenter)

    await swl.run()


async def run():
    app = LpAppFramework()
    async with app():
        # await dbg_tests_parts_watchlist(app)
        # await dbg_run_watchlist(app)
        await dbg_run_track_of_completed_swaps(app)


if __name__ == '__main__':
    asyncio.run(run())
