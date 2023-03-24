import asyncio
import logging

from services.jobs.fetch.flipside import FlipSideConnector
from services.jobs.fetch.killed_rune import KilledRuneFetcher, DEFAULT_API_URL
from tools.lib.lp_common import LpAppFramework


async def simple_fetch(app):
    killed_rune_fetcher = KilledRuneFetcher(app.deps)
    r = await killed_rune_fetcher.fetch()
    print(r[0])
    print(r[1])


async def flipside_test(app):
    fs = FlipSideConnector(app.deps.session)
    data = await fs.request_daily_series(DEFAULT_API_URL)
    print(data)


async def main():
    app = LpAppFramework(log_level=logging.INFO)
    async with app:
        await app.prepare(brief=True)

        await simple_fetch(app)
        # await flipside_test(app)


if __name__ == '__main__':
    asyncio.run(main())
