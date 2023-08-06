import asyncio

from aiothornode.connector import ThorConnector

from services.dialog.picture.price_picture import price_graph_from_db
from services.jobs.fetch.gecko_price import fill_rune_price_from_gecko
from services.jobs.fetch.pool_price import PoolFetcher, PoolInfoFetcherMidgard
from services.lib.constants import NetworkIdents
from services.lib.depcont import DepContainer
from services.notify.types.best_pool_notify import BestPoolsNotifier
from tools.lib.lp_common import LpAppFramework, save_and_show_pic


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


async def demo_price_graph(app, fill=False):
    if fill:
        await fill_rune_price_from_gecko(app.deps.db, include_fake_det=True)
    loc = app.deps.loc_man.default
    graph, graph_name = await price_graph_from_db(app.deps, loc)

    # sender = PriceNotifier(app.deps)
    # hist_prices = await sender.historical_get_triplet()
    #
    # net_stats, market_info = await debug_get_rune_market_data(app)
    #
    # report = PriceReport(*hist_prices, market_info, last_ath, btc_price)
    # caption = loc.notification_text_price_update(report, ath, halted_chains=self.deps.halted_chains)
    #
    save_and_show_pic(graph, graph_name)


async def main():
    app = LpAppFramework()
    async with app(brief=True):
        # await demo_cache_blocks(app)
        # await demo_top_pools(app)
        await demo_price_graph(app)


if __name__ == '__main__':
    asyncio.run(main())
