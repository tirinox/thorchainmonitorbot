import asyncio
import logging
from pprint import pprint

from services.jobs.fetch.pol import POLFetcher
from services.notify.types.pol_notify import POLNotifier
from tools.lib.lp_common import LpAppFramework


async def demo_pol_1(app: LpAppFramework):
    pol_fetcher = POLFetcher(app.deps)
    r = await pol_fetcher.fetch()
    pprint(r)
    pprint(r._asdict())


async def demo_pol_pipeline(app: LpAppFramework):
    ...
    pol_fetcher = POLFetcher(app.deps)
    pol_notifier = POLNotifier(app.deps)
    pol_fetcher.add_subscriber(pol_notifier)

    await pol_fetcher.run()


async def main():
    app = LpAppFramework(log_level=logging.INFO)
    async with app:
        # await demo_pol_1(app)
        await demo_pol_pipeline(app)


if __name__ == '__main__':
    asyncio.run(main())
