import asyncio
import logging

from services.jobs.fetch.runeyield import AsgardConsumerConnectorV1
from services.jobs.fetch.runeyield.lp_my import HomebrewLPConnector
from services.jobs.fetch.tx import TxFetcher
from services.lib.utils import setup_logs
from tools.dbg_lp import LpTesterBase


async def test_get_user_lp_actions(lpgen: LpTesterBase):
    txf = TxFetcher(lpgen.deps)
    res = await txf.fetch_user_tx('tthor1qtedshax98p3v9al3pqjrfmf32xmrlfzs7lxg2', liquidity_change_only=True)
    for tx in res:
        print(tx, end='\n-----\n')


ADDR = ''
# POOL = 'BNB.BUSD-BD1'
POOL = 'BNB.ETHBULL-D33'


# ADDR = 'bnb10z6pvckwlpl630nujweugqrqkdfmnxnrplssav'
# POOL = 'BNB.SXP-CCC'


async def show_me_example_liquidity():
    lpgen = LpTesterBase(AsgardConsumerConnectorV1)
    async with lpgen:
        liq = await lpgen.rune_yield._fetch_one_pool_liquidity_info(ADDR, POOL)
        print(liq)


async def test_summary_of_all_pools(lpgen: LpTesterBase):
    pools = await lpgen.rune_yield.get_my_pools(ADDR)
    charts, reports = await lpgen.rune_yield.generate_yield_summary(ADDR, pools)
    for r in reports:
        print(r.fees)
        print('------')


async def test_1_pool(lpgen: LpTesterBase):
    report = await lpgen.rune_yield.generate_yield_report_single_pool(ADDR, POOL)
    print(report)


async def main():
    lpgen = LpTesterBase(HomebrewLPConnector)
    async with lpgen:
        await test_1_pool(lpgen)


if __name__ == "__main__":
    setup_logs(logging.INFO)
    # asyncio.run(show_me_example_liquidity())
    asyncio.run(main())
