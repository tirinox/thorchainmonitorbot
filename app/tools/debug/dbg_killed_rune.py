import asyncio
import logging

from services.jobs.fetch.killed_rune import KilledRuneFetcher
from tools.lib.lp_common import LpAppFramework


async def main():
    lp_app = LpAppFramework(log_level=logging.INFO)
    async with lp_app:
        await lp_app.prepare(brief=True)

        killed_rune_fetcher = KilledRuneFetcher(lp_app.deps)
        r = await killed_rune_fetcher.fetch()
        print(r[0])


if __name__ == '__main__':
    asyncio.run(main())
