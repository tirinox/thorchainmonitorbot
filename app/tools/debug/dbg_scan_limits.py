import asyncio

from jobs.limit_recorder import LimitSwapStatsRecorder
from jobs.scanner.limit_detector import LimitSwapDetector
from jobs.scanner.scan_cache import BlockScannerCached
from tools.lib.lp_common import LpAppFramework


async def dbg_limit_detector_continuous(app: LpAppFramework, last_block=0):
    block_scanner = BlockScannerCached(app.deps, last_block=last_block)

    limit_swap_detector = LimitSwapDetector(app.deps)
    block_scanner.add_subscriber(limit_swap_detector)

    limit_swap_recorder = LimitSwapStatsRecorder(app.deps)
    limit_swap_detector.add_subscriber(limit_swap_recorder)

    await block_scanner.run()


async def run():
    app = LpAppFramework()
    async with app:
        await dbg_limit_detector_continuous(app)


if __name__ == '__main__':
    asyncio.run(run())
