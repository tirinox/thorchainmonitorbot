import asyncio

from tools.lib.lp_common import LpAppFramework

async def dbg_limit_detector_continuous(app: LpAppFramework):



async def run():
    app = LpAppFramework()
    async with app:
        await dbg_limit_detector_continuous(app)


if __name__ == '__main__':
    asyncio.run(run())
