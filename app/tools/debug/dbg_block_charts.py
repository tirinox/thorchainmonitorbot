import asyncio
import logging

from services.jobs.fetch.last_block import LastBlockFetcher
from services.lib.utils import setup_logs
from services.notify.types.block_notify import BlockHeightNotifier
from tools.lib.lp_common import LpAppFramework


def my_test_smart_block_time_estimator():
    pts = [
        (1, 1),
        (2, 2),
        (3, 3),
        (22, 3),
        (25, 4),
        (26, 5),
        (30, 6),
        (45, 7),
        (60, 8),
        (66, 9)
    ]
    r = BlockHeightNotifier.smart_block_time_estimator(pts, 10)
    print(f'{pts = }:\nResult: {r}')

    pts = [
        (v, v * v) for v in range(51)
    ]
    r = BlockHeightNotifier.smart_block_time_estimator(pts, 10)
    print(f'{pts = }:\nResult: {r}')


async def my_test_block_fetch(app: LpAppFramework):
    async with app:
        lbf = LastBlockFetcher(app.deps)
        block_not = BlockHeightNotifier(app.deps)
        lbf.subscribe(block_not)
        await lbf.run()


async def main():
    my_test_smart_block_time_estimator()
    return

    app = LpAppFramework()

    async with app:
        await my_test_block_fetch(app)


if __name__ == "__main__":
    # test_upd()
    setup_logs(logging.INFO)
    asyncio.run(main())
