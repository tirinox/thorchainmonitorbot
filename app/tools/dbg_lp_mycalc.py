import asyncio
import logging

from services.jobs.fetch.tx import TxFetcher
from tools.dbg_lp import LpTesterBase


async def test_get_user_lp_actions(lpgen: LpTesterBase):
    txf = TxFetcher(lpgen.deps)
    res = await txf.fetch_user_tx('tthor1qtedshax98p3v9al3pqjrfmf32xmrlfzs7lxg2', liquidity_change_only=True)
    for tx in res:
        print(tx, end='\n-----\n')


async def main():
    lpgen = LpTesterBase()
    async with lpgen:
        await test_get_user_lp_actions(lpgen)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
