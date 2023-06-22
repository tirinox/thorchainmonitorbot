import asyncio
import logging

from services.jobs.fetch.cap import CapInfoFetcher
from tools.lib.lp_common import LpAppFramework


async def main():
    lp_app = LpAppFramework(log_level=logging.INFO)
    async with lp_app:
        await lp_app.prepare(brief=True)
        cap_fetcher = CapInfoFetcher(lp_app.deps)
        data = await cap_fetcher.fetch()
        print(data)


if __name__ == '__main__':
    asyncio.run(main())
