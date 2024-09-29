import asyncio
import logging
import time

from comm.localization.languages import Language
from comm.localization.manager import BaseLocalization
from jobs.fetch.circulating import RuneCirculatingSupplyFetcher
from jobs.fetch.fair_price import RuneMarketInfoFetcher
from jobs.fetch.net_stats import NetworkStatisticsFetcher
from lib.texts import sep
from tools.lib.lp_common import LpAppFramework


async def my_test_circulating_telegram(lp_app: LpAppFramework):
    rmf = lp_app.deps.rune_market_fetcher
    rmf: RuneMarketInfoFetcher
    # todo: debug
    info = await rmf.get_rune_market_info()
    # loc: BaseLocalization = lp_app.deps.loc_man.default
    loc: BaseLocalization = lp_app.deps.loc_man.get_from_lang(Language.ENGLISH_TWITTER)
    await lp_app.send_test_tg_message(loc.text_metrics_supply(info))


async def my_test_circulating(lp_app: LpAppFramework):
    rmf = lp_app.deps.rune_market_fetcher
    rmf: RuneMarketInfoFetcher

    t0 = time.perf_counter()

    info = await rmf.get_rune_market_info()
    t1 = time.perf_counter()
    print(f'[{t1 - t0}]: {info}')
    sep()

    print('next? ------>')
    info = await rmf.get_rune_market_info()
    t1 = time.perf_counter()
    print(f'[{t1 - t0}]: {info}')

    print('waiting....')
    await asyncio.sleep(5.5)
    sep()

    print('and once again! (cached data had to expire now)')
    info = await rmf.get_rune_market_info()
    t1 = time.perf_counter()
    print(f'[{t1 - t0}]: {info}')
    sep()


def get_rune_supply_fetcher(app: LpAppFramework):
    return RuneCirculatingSupplyFetcher(
        app.deps.session, app.deps.thor_connector,
        midgard=app.deps.midgard_connector
    )


async def debug_circulating_rune_fetcher(app: LpAppFramework):
    supply = get_rune_supply_fetcher(app)
    data = await supply.fetch()

    print(data)
    print(data.holders)


async def debug_treasury_lp(app: LpAppFramework):
    supply = get_rune_supply_fetcher(app)
    data = await supply.get_treasury_lp_value()
    print(data)


async def debug_circulating_rune_message(app: LpAppFramework):
    fetcher_stats = NetworkStatisticsFetcher(app.deps)
    app.deps.net_stats = await fetcher_stats.fetch()

    sep()

    # cached: no pool/bond info!
    market_info = await app.deps.rune_market_fetcher.get_rune_market_info()

    locs = app.deps.loc_man.all
    # locs = [app.deps.loc_man[Language.ENGLISH_TWITTER]]
    for loc in locs:
        text = loc.text_metrics_supply(market_info)
        print(text)
        await app.send_test_tg_message(text)
        sep()


async def main():
    lp_app = LpAppFramework(log_level=logging.INFO)
    async with lp_app():
        # await my_test_circulating(lp_app)
        await my_test_circulating_telegram(lp_app)
        # await debug_circulating_rune_message(lp_app)
        # await debug_circulating_rune_fetcher(lp_app)
        # await debug_treasury_lp(lp_app)


if __name__ == '__main__':
    asyncio.run(main())
