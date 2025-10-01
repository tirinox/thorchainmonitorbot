import asyncio
import logging

from tools.lib.lp_common import LpAppFramework


async def dbg_tcy_data_collect(app):
    ...


async def main():
    app = LpAppFramework(log_level=logging.DEBUG)
    async with app(brief=True):
        await dbg_tcy_data_collect(app)


if __name__ == '__main__':
    asyncio.run(main())
