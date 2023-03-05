import asyncio
import logging
from pprint import pprint

from services.jobs.fetch.pol import POLFetcher
from services.lib.constants import NetworkIdents, STAGENET_RESERVE_ADDRESS
from services.notify.types.pol_notify import POLNotifier
from tools.lib.lp_common import LpAppFramework


def get_reserve_address(app: LpAppFramework):
    reserve_address = STAGENET_RESERVE_ADDRESS if app.deps.cfg.network_id == NetworkIdents.STAGENET_MULTICHAIN else None
    return reserve_address


async def demo_pol_1(app: LpAppFramework):
    pol_fetcher = POLFetcher(app.deps, reserve_address=get_reserve_address(app))
    r = await pol_fetcher.fetch()
    pprint(r)
    pprint(r._asdict())


async def demo_pol_pipeline(app: LpAppFramework):
    pol_fetcher = POLFetcher(app.deps, reserve_address=get_reserve_address(app))
    pol_notifier = POLNotifier(app.deps)
    pol_fetcher.add_subscriber(pol_notifier)
    pol_fetcher.add_subscriber(pol_notifier)

    pol_notifier.add_subscriber(app.deps.alert_presenter)

    await pol_fetcher.run()


async def main():
    app = LpAppFramework(log_level=logging.INFO, network=NetworkIdents.STAGENET_MULTICHAIN)

    async with app:
        # await demo_pol_1(app)
        await demo_pol_pipeline(app)


if __name__ == '__main__':
    asyncio.run(main())
