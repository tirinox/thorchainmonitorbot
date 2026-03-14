import asyncio

from jobs.limit_recorder import LimitSwapStatsRecorder
from jobs.scanner.limit_detector import LimitSwapDetector
from jobs.scanner.scan_cache import BlockScannerCached
from tools.lib.lp_common import LpAppFramework


async def dbg_limit_detector_continuous(app: LpAppFramework, last_block=0):
    d = app.deps
    if not last_block:
        # last_block = await d.last_block_cache.get_thor_block()
        # last_block -= 1000
        last_block = 24832335
    block_scanner = BlockScannerCached(d, last_block=last_block)

    limit_swap_detector = LimitSwapDetector(d)
    block_scanner.add_subscriber(limit_swap_detector)

    limit_swap_recorder = LimitSwapStatsRecorder(d)
    limit_swap_detector.add_subscriber(limit_swap_recorder)

    await block_scanner.run()


async def run():
    app = LpAppFramework()
    async with app:
        await dbg_limit_detector_continuous(app)


if __name__ == '__main__':
    asyncio.run(run())
