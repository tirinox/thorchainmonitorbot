import asyncio

from jobs.scanner.scan_cache import BlockScannerCached
from notify.public.s_swap_notify import StreamingSwapStartTxNotifier
from tools.lib.lp_common import LpAppFramework


async def dbg_run_continuous(app: LpAppFramework, start_block=0):
    d = app.deps

    if start_block is not None and start_block < 0:
        thor = await app.deps.last_block_cache.get_thor_block()
        assert thor > 0
        start_block = thor + start_block
    else:
        start_block = 0

    d.block_scanner = BlockScannerCached(d, last_block=start_block)

    stream_swap_notifier = StreamingSwapStartTxNotifier(d)
    d.block_scanner.add_subscriber(stream_swap_notifier)
    stream_swap_notifier.add_subscriber(d.alert_presenter)

    await d.block_scanner.run()
    await asyncio.sleep(5.0)


async def run():
    app = LpAppFramework()
    async with app:
        # await dbg_run_continuous(app, start_block=-300)
        await dbg_run_continuous(app, start_block=23997518 - 10)


if __name__ == '__main__':
    asyncio.run(run())
