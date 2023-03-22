import asyncio
import logging

from tools.lib.lp_common import LpAppFramework


async def main():
    lp_app = LpAppFramework(log_level=logging.INFO)
    async with lp_app:
        await lp_app.prepare(brief=True)

        pass  # todo


if __name__ == '__main__':
    asyncio.run(main())
