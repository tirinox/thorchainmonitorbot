import asyncio

from lib.midgard.connector import MidgardConnector
from lib.texts import sep
from tools.lib.lp_common import LpAppFramework


async def my_test_midgard1():
    lp_app = LpAppFramework()
    async with lp_app:
        await lp_app.prepare(brief=True)
        mdg: MidgardConnector = lp_app.deps.midgard_connector

        sep()
        print('Starting quering Midgards')
        pools = await mdg.request('v2/network')
        print(pools)


async def main():
    await my_test_midgard1()


if __name__ == '__main__':
    asyncio.run(main())
