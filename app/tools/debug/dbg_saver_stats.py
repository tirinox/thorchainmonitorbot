import asyncio

from services.jobs.fetch.pool_price import PoolFetcher
from services.notify.types.savers_stats_notify import SaversStatsNotifier
from tools.lib.lp_common import LpAppFramework


async def demo_collect_stat(app: LpAppFramework):
    pf: PoolFetcher = app.deps.pool_fetcher
    pool_map = await pf.load_pools()
    ssn = SaversStatsNotifier(app.deps)
    data = await ssn.get_all_savers(pool_map)
    print(data)


async def run():
    app = LpAppFramework()
    async with app(brief=True):
        await demo_collect_stat(app)


if __name__ == '__main__':
    asyncio.run(run())
