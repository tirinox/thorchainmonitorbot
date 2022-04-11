import asyncio
import logging

from services.jobs.fetch.fair_price import RuneMarketInfoFetcher
from services.lib.utils import setup_logs
from tools.lib.lp_common import LpAppFramework


async def my_test_price_cache():
    lp_app = LpAppFramework(log_level=logging.INFO)
    async with lp_app:
        f = RuneMarketInfoFetcher(lp_app.deps)
        print(await f.get_rune_market_info())

        print(await f.get_rune_market_info())


async def main():
    await my_test_price_cache()


if __name__ == "__main__":
    asyncio.run(main())
