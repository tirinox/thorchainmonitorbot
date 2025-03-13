import asyncio
import json

from api.aionode.connector import ThorConnector
from comm.picture.price_picture import price_graph_from_db
from jobs.fetch.fair_price import RuneMarketInfoFetcher
from jobs.fetch.gecko_price import fill_rune_price_from_gecko
from jobs.fetch.pool_price import PoolFetcher, PoolInfoFetcherMidgard
from lib.date_utils import DAY
from lib.depcont import DepContainer
from lib.texts import sep
from lib.utils import recursive_asdict
from models.price import LastPriceHolder
from notify.alert_presenter import AlertPresenter
from notify.public.best_pool_notify import BestPoolsNotifier
from notify.public.price_notify import PriceNotifier
from tools.lib.lp_common import LpAppFramework, save_and_show_pic


def set_network(d: DepContainer, network_id: str):
    d.cfg.network_id = network_id
    d.thor_connector = ThorConnector(d.cfg.get_thor_env_by_network_id(), d.session)


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


async def demo_old_price_graph(app, fill=False):
    if fill:
        await fill_rune_price_from_gecko(app.deps.db, include_fake_det=True)
    loc = app.deps.loc_man.default
    graph, graph_name = await price_graph_from_db(app.deps, loc)
    save_and_show_pic(graph, graph_name)


async def _create_price_alert(app, fill=False):
    # use: redis_copy_keys.py to copy redis keys from prod to local

    if fill:
        await fill_rune_price_from_gecko(app.deps.db, include_fake_det=True)

    await app.deps.pool_fetcher.run_once()
    await app.deps.fetcher_chain_state.run_once()

    print(f'All chains: {app.deps.chain_info.state_list}')

    price_notifier = PriceNotifier(app.deps)

    market_fetcher = RuneMarketInfoFetcher(app.deps)
    market_info = await market_fetcher.fetch()

    event = await price_notifier.make_event(
        market_info,
        ath=False, last_ath=None
    )
    return event


async def dbg_load_latest_price_data_and_save_as_demo(app, fill=False):
    event = await _create_price_alert(app, fill)
    sep()

    raw_data = recursive_asdict(event, add_properties=True)
    del raw_data['market_info']['pools']

    raw_data = {
        "template_name": "price.jinja2",
        "parameters": {
            **raw_data,
            "_width": 1200,
            "_height": 1200
        }
    }

    json_data = json.dumps(raw_data, indent=2)
    sep()
    print(json_data)
    sep()

    demo_file = './renderer/demo/price-gen.json'
    with open(demo_file, 'w') as f:
        f.write(json_data)
        print(f'Saved to {demo_file!r}')


async def find_anomaly(app, start=13225800, steps=200):
    block = start
    holder = LastPriceHolder()
    while block < start + steps:
        pools = await app.deps.pool_fetcher.load_pools(block, caching=True)
        holder.update_pools(pools)

        print(f'Block {block}: {len(pools)} pools, rune price = {holder.usd_per_rune}')

        block += 1


async def debug_load_pools(app: LpAppFramework):
    await app.deps.last_block_fetcher.run_once()

    pf = app.deps.pool_fetcher
    pools = await pf.load_pools(13345278)
    print(len(pools))
    pools = await pf.load_pools(13345278)
    print(len(pools))
    sep()

    pools = await pf.load_pools()
    print(len(pools))
    sep()
    pools = await pf.load_pools()
    print(len(pools))


async def dbg_save_market_info(app):
    info = await app.deps.rune_market_fetcher.fetch()
    sep()
    print(json.dumps(info, indent=2))
    sep()


async def dbg_new_price_picture(app):
    event = await _create_price_alert(app)

    ap: AlertPresenter = app.deps.alert_presenter
    await ap.on_data(None, event)
    await asyncio.sleep(5.0)


async def main():
    app = LpAppFramework()
    async with app(brief=True):
        # await find_anomaly(app)
        # await demo_cache_blocks(app)
        # await demo_top_pools(app)
        # await dbg_load_latest_price_data_and_save_as_demo(app, fill=False)
        # await debug_load_pools(app)
        # await dbg_save_market_info(app)
        await dbg_new_price_picture(app)


if __name__ == '__main__':
    asyncio.run(main())
