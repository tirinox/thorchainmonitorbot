import asyncio
import logging

from services.jobs.fetch.pool_price import PoolPriceFetcher
from services.jobs.fetch.runeyield.lp_my import HomebrewLPConnector
from services.jobs.fetch.tx import TxFetcher
from services.lib.utils import setup_logs
from tools.dbg_lp import LpTesterBase


async def test_get_user_lp_actions(lpgen: LpTesterBase):
    txf = TxFetcher(lpgen.deps)
    res = await txf.fetch_user_tx('tthor1qtedshax98p3v9al3pqjrfmf32xmrlfzs7lxg2', liquidity_change_only=True)
    for tx in res:
        print(tx, end='\n-----\n')


async def test_filter_my_tx(lpgen: LpTesterBase):
    await lpgen.rune_yield.generate_yield_report_single_pool(
        'bnb10z6pvckwlpl630nujweugqrqkdfmnxnrplssav',
        'BNB.SXP-CCC')


async def main():
    lpgen = LpTesterBase(HomebrewLPConnector)
    async with lpgen:
        # await test_get_user_lp_actions(lpgen)
        await test_filter_my_tx(lpgen)


if __name__ == "__main__":
    setup_logs(logging.INFO)
    asyncio.run(main())
