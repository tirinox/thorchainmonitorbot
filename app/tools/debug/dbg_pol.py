import asyncio
import logging
from pprint import pprint
from typing import Optional

from aionode.types import ThorRunePoolPOL

from services.jobs.fetch.pol import RunePoolFetcher
from services.lib.constants import NetworkIdents, STAGENET_RESERVE_ADDRESS
from services.lib.date_utils import DAY
from services.lib.depcont import DepContainer
from services.lib.money import distort_randomly
from services.models.pol import POLState, AlertPOL
from services.notify.types.pol_notify import POLNotifier
from tools.lib.lp_common import LpAppFramework


def get_reserve_address(app: LpAppFramework):
    reserve_address = STAGENET_RESERVE_ADDRESS if app.deps.cfg.network_id == NetworkIdents.STAGENET_MULTICHAIN else None
    return reserve_address


async def demo_pol_1(app: LpAppFramework):
    await app.deps.pool_fetcher.run_once()
    await app.deps.mimir_const_fetcher.run_once()
    pol_fetcher = RunePoolFetcher(app.deps, reserve_address=get_reserve_address(app))
    r = await pol_fetcher.fetch()
    pprint(r)
    pprint(r._asdict())

    await app.deps.alert_presenter.on_data(None, r)
    await asyncio.sleep(3)



class DbgPOLNotifier(POLNotifier):
    def __init__(self, deps: DepContainer, mode):
        super().__init__(deps)
        self.mode = mode

    async def find_stats_ago(self, period_ago) -> Optional[AlertPOL]:
        if self.mode == 'random_hardcode':
            return await self._find_stats_ago_random_hardcode(period_ago)
        elif self.mode == 'normal':
            return await super().find_stats_ago(period_ago)
        elif self.mode == 'random_value':
            data = await super().find_stats_ago(period_ago)
            if data:
                data = data._replace(
                    current=data.current._replace(
                        value=data.current.value._replace(
                            value=distort_randomly(data.current.value.value)
                        )
                    )
                )
                return data

    async def _find_stats_ago_random_hardcode(self, period_ago) -> Optional[AlertPOL]:
        pol_state = POLState(
            usd_per_rune=1.5,
            value=ThorRunePoolPOL(
                current_deposit=distort_randomly(5028203433),  # = rune_deposited - rune_withdrawn
                pnl=distort_randomly(1071851731),
                rune_deposited=distort_randomly(9932906488, up_only=True),
                rune_withdrawn=distort_randomly(4904703055, up_only=True),
                value=distort_randomly(6100055164, up_only=True),
            ))
        return AlertPOL(
            current=pol_state,
            membership=[],
        )


async def demo_pol_pipeline(app: LpAppFramework):
    pol_fetcher = RunePoolFetcher(app.deps, reserve_address=get_reserve_address(app))

    pol_notifier = DbgPOLNotifier(app.deps, mode='random_value')
    pol_fetcher.add_subscriber(pol_notifier)

    pol_notifier.add_subscriber(app.deps.alert_presenter)

    await pol_fetcher.run()


async def demo_pol_history(app: LpAppFramework):
    pol_notifier = POLNotifier(app.deps)
    history = await pol_notifier.last_points(DAY)
    print(history)


async def main():
    # app = LpAppFramework(log_level=logging.INFO, network=NetworkIdents.STAGENET_MULTICHAIN)
    app = LpAppFramework(log_level=logging.INFO)

    async with app:
        await demo_pol_1(app)
        # await demo_pol_pipeline(app)
        # await demo_pol_history(app)


if __name__ == '__main__':
    asyncio.run(main())
