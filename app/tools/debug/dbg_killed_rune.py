import asyncio
import logging

from services.jobs.fetch.flipside import FlipSideConnector
from services.jobs.fetch.killed_rune import KilledRuneFetcher, DEFAULT_API_URL, KilledRuneStore
from services.notify.types.supply_notify import SupplyNotifier
from tools.lib.lp_common import LpAppFramework


async def simple_fetch(app):
    d = app.deps
    killed_rune_fetcher = KilledRuneFetcher(d)

    kr_store = KilledRuneStore(d)
    killed_rune_fetcher.add_subscriber(kr_store)

    await killed_rune_fetcher.run_once()
    print(d.killed_rune)

    supply_notifier = SupplyNotifier(d)
    await supply_notifier._cd.clear()
    d.pool_fetcher.add_subscriber(supply_notifier)
    await d.pool_fetcher.run_once()
    await asyncio.sleep(5)


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
