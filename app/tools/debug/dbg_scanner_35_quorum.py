import asyncio

from jobs.scanner.native_scan import BlockScanner
from jobs.user_counter import UserCounterMiddleware
from tools.lib.lp_common import LpAppFramework


async def demo_one_block(app: LpAppFramework, block_no):
    d = app.deps
    d.block_scanner.initial_sleep = 0

    # await d.pool_fetcher.run_once()
    # d.last_block_fetcher.add_subscriber(d.last_block_store)
    # await d.last_block_fetcher.run_once()

    # block = await d.block_scanner.fetch_one_block(block_no)
    # print(block)

    d.user_counter = UserCounterMiddleware(d)
    d.block_scanner.add_subscriber(d.user_counter)

    await d.block_scanner.run()


async def run():
    app = LpAppFramework()
    async with app(brief=True):
        await demo_one_block(app, 20947105)


if __name__ == '__main__':
    asyncio.run(run())
