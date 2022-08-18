import asyncio
import logging
import time

from localization.languages import Language
from localization.manager import BaseLocalization
from services.jobs.fetch.fair_price import RuneMarketInfoFetcher
from services.jobs.fetch.killed_rune import KilledRuneFetcher, KilledRuneStore
from services.lib.texts import sep
from tools.lib.lp_common import LpAppFramework


async def manually_load_killed_rune(lp_app: LpAppFramework):
    krf = KilledRuneFetcher(lp_app.deps)
    kr_store = KilledRuneStore(lp_app.deps)
    krf.subscribe(kr_store)
    data = await krf.fetch()
    await krf.pass_data_to_listeners(data)


async def my_test_circulating_telegram(lp_app: LpAppFramework):
    print(lp_app.deps.killed_rune)

    rmf = lp_app.deps.rune_market_fetcher
    rmf: RuneMarketInfoFetcher
    # todo: debug
    info = await rmf.get_rune_market_info()
    # loc: BaseLocalization = lp_app.deps.loc_man.default
    loc: BaseLocalization = lp_app.deps.loc_man.get_from_lang(Language.ENGLISH_TWITTER)
    await lp_app.send_test_tg_message(loc.text_metrics_supply(info, lp_app.deps.killed_rune))


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


async def main():
    lp_app = LpAppFramework(log_level=logging.INFO)
    async with lp_app():
        # await my_test_circulating(lp_app)
        await my_test_circulating_telegram(lp_app)


if __name__ == '__main__':
    asyncio.run(main())
