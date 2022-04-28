import asyncio
import logging
import time

from localization import BaseLocalization
from services.jobs.fetch.fair_price import RuneMarketInfoFetcher
from services.lib.utils import sep
from tools.lib.lp_common import LpAppFramework


async def my_test_circulating_telegram(lp_app: LpAppFramework):
    rmf = lp_app.deps.rune_market_fetcher
    rmf: RuneMarketInfoFetcher
    info = await rmf.get_rune_market_info()
    loc: BaseLocalization = lp_app.deps.loc_man.default
    # loc: BaseLocalization = lp_app.deps.loc_man.get_from_lang('rus')
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


async def main():
    lp_app = LpAppFramework(log_level=logging.INFO)
    async with lp_app:
        await lp_app.prepare(brief=True)
        # await my_test_circulating(lp_app)
        await my_test_circulating_telegram(lp_app)


if __name__ == '__main__':
    asyncio.run(main())
