import asyncio

from aiothornode.connector import ThorConnector

from services.jobs.fetch.pool_price import PoolFetcher, PoolInfoFetcherMidgard
from services.lib.constants import NetworkIdents
from services.lib.depcont import DepContainer
from services.notify.types.best_pool_notify import BestPoolsNotifier
from tools.lib.lp_common import LpAppFramework


def set_network(d: DepContainer, network_id: str):
    d.cfg.network_id = network_id
    d.thor_connector = ThorConnector(d.cfg.get_thor_env_by_network_id(), d.session)


async def demo_thor_pools_caching_mctn(d: DepContainer):
    set_network(d, NetworkIdents.TESTNET_MULTICHAIN)

    ppf = PoolFetcher(d)
    pp = await ppf.load_pools(caching=True, height=501)
    print(pp)


async def demo_price_continuously(d: DepContainer):
    ppf = PoolFetcher(d)
    d.thor_connector = ThorConnector(d.cfg.get_thor_env_by_network_id(), d.session)
    while True:
        await ppf.fetch()
        await asyncio.sleep(2.0)


async def demo_get_pool_info_midgard(d: DepContainer):
    ppf = PoolInfoFetcherMidgard(d, 10)
    pool_map = await ppf.fetch()
    print(pool_map)


async def demo_cache_blocks(app: LpAppFramework):
    await app.deps.last_block_fetcher.run_once()
    last_block = app.deps.last_block_store.last_thor_block
    print(last_block)

    pf: PoolFetcher = app.deps.pool_fetcher
    pools = await pf.load_pools(7_000_000, caching=True)
    print(pools)

    pools = await pf.load_pools(8_200_134, caching=True)
    print(pools)

    pools = await pf.load_pools(8_200_136, caching=True)
    print(pools)


async def demo_top_pools(app: LpAppFramework):
    d = app.deps
    fetcher_pool_info = PoolInfoFetcherMidgard(d, 1)
    d.best_pools_notifier = BestPoolsNotifier(d)
    await d.best_pools_notifier._cooldown.clear()
    fetcher_pool_info.add_subscriber(d.best_pools_notifier)
    await fetcher_pool_info.run_once()


async def main():
    app = LpAppFramework()
    async with app(brief=True):
        # await demo_cache_blocks(app)
        await demo_top_pools(app)


if __name__ == '__main__':
    asyncio.run(main())
