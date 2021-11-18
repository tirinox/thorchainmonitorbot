import asyncio
import logging

from services.jobs.fetch.last_block import LastBlockFetcher
from services.lib.utils import setup_logs
from services.notify.types.block_notify import BlockHeightNotifier
from tools.lib.lp_common import LpAppFramework


async def my_test_block_fetch(app: LpAppFramework):
    async with app:
        lbf = LastBlockFetcher(app.deps)
        block_not = BlockHeightNotifier(app.deps)
        lbf.subscribe(block_not)
        await lbf.run()


async def main():
    app = LpAppFramework()

    async with app:
        await my_test_block_fetch(app)


if __name__ == "__main__":
    # test_upd()
    setup_logs(logging.INFO)
    asyncio.run(main())
