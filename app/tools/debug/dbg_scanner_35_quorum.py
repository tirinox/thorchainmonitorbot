import asyncio

from jobs.scanner.block_result import BlockResult
from tools.lib.lp_common import LpAppFramework


async def dbg_failing_scan_date(app: LpAppFramework, block_no=25615925):
    # load block from network
    block: BlockResult = await app.deps.block_scanner.fetch_one_block(block_no)
    print('block', block_no, 'date', block.timestamp)


async def demo_one_block(app: LpAppFramework, block_no):
    d = app.deps
    d.block_scanner.initial_sleep = 0

    d.block_scanner.add_subscriber(d.user_counter)

    await d.block_scanner.run()


async def run():
    app = LpAppFramework()
    async with app:
        await demo_one_block(app, 25624623)
        await dbg_failing_scan_date(app, 25624623)


if __name__ == '__main__':
    asyncio.run(run())
