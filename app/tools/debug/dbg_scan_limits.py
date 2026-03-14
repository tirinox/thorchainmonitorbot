import asyncio
import json

from jobs.limit_recorder import LimitSwapStatsRecorder
from jobs.scanner.limit_detector import LimitSwapDetector
from jobs.scanner.scan_cache import BlockScannerCached
from tools.lib.lp_common import LpAppFramework


async def dbg_limit_detector_continuous(app: LpAppFramework, last_block=0):
    d = app.deps
    if not last_block:
        # last_block = await d.last_block_cache.get_thor_block()
        # last_block -= 10000
        last_block = 24802335
    block_scanner = BlockScannerCached(d, last_block=last_block)

    limit_swap_detector = LimitSwapDetector(d)
    block_scanner.add_subscriber(limit_swap_detector)

    limit_swap_recorder = LimitSwapStatsRecorder(d)
    limit_swap_detector.add_subscriber(limit_swap_recorder)

    await block_scanner.run()


async def dbg_limit_last_data(app: LpAppFramework, days: int = 14):
    d = app.deps
    recorder = LimitSwapStatsRecorder(d)

    daily = await recorder.get_daily_data(days=2)
    summary = await recorder.get_summary(days=days)

    latest = daily[-1] if daily else {}

    print('Latest daily limit-swap data:')
    print(json.dumps(latest, indent=2, sort_keys=True))
    print()
    print(f'Limit-swap summary for last {days} days:')
    print(json.dumps(summary, indent=2, sort_keys=True))


async def run():
    app = LpAppFramework()
    async with app:
        await dbg_limit_detector_continuous(app)
        # await dbg_limit_last_data(app)


if __name__ == '__main__':
    asyncio.run(run())
