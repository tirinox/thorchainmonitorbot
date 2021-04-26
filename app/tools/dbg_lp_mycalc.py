import asyncio
import logging

from services.jobs.fetch.runeyield import AsgardConsumerConnectorV1
from services.jobs.fetch.runeyield.lp_my import HomebrewLPConnector
from services.jobs.fetch.tx import TxFetcher
from services.lib.utils import setup_logs, load_pickle, save_pickle
from tools.dbg_lp import LpTesterBase


async def test_get_user_lp_actions(lpgen: LpTesterBase):
    txf = TxFetcher(lpgen.deps)
    res = await txf.fetch_user_tx('tthor1qtedshax98p3v9al3pqjrfmf32xmrlfzs7lxg2', liquidity_change_only=True)
    for tx in res:
        print(tx, end='\n-----\n')


# ADDR = 'bnb1nqcg6f8cfc6clhm8hac6002xq3h7l7gxh3qm34'  # to much stake/unstake

ADDR = 'bnb1v9jldefnx0mngfetkwuczzxerrgw6ncvlukad5'
POOL = 'BNB.USDT-6D8'
# POOL = 'BNB.ETHBULL-D33'

ADDR_MCTN = 'tthor1erl5a09ahua0umwcxp536cad7snerxt4eflyq0'
POOL_MCTN = ''


# ADDR = 'bnb10z6pvckwlpl630nujweugqrqkdfmnxnrplssav'
# POOL = 'BNB.SXP-CCC'


async def show_me_example_liquidity():
    lpgen = LpTesterBase(AsgardConsumerConnectorV1)
    async with lpgen:
        liq = await lpgen.rune_yield._fetch_one_pool_liquidity_info(ADDR, POOL)
        print(liq)


async def test_summary_of_all_pools(lpgen: LpTesterBase):
    pools = await lpgen.rune_yield.get_my_pools(ADDR)
    yield_report = await lpgen.rune_yield.generate_yield_summary(ADDR, pools)
    for r in yield_report.reports:
        print(r.fees)
        print('------')


async def test_1_pool(lpgen: LpTesterBase):
    report = await lpgen.rune_yield.generate_yield_report_single_pool(ADDR, POOL)
    print(report)


async def test_charts(lpgen: LpTesterBase, address=ADDR):
    rl = lpgen.rune_yield

    data_path = '../../lp_chart_data_many.pickle'

    data = load_pickle(data_path)
    if data:
        user_txs, historic_all_pool_states, current_pools_details, pools = data
    else:
        pools = await rl.get_my_pools(address)
        user_txs = await rl._get_user_tx_actions(address)

        historic_all_pool_states, current_pools_details = await asyncio.gather(
            rl._fetch_historical_pool_states(user_txs),
            rl._get_details_of_staked_pools(address, pools)
        )
        save_pickle(data_path, (user_txs, historic_all_pool_states, current_pools_details, pools))

    day_units = await rl._get_charts(user_txs, current_pools_details, historic_all_pool_states, days=300)
    print(day_units)


async def main():
    lpgen = LpTesterBase(HomebrewLPConnector)
    async with lpgen:
        # await test_1_pool(lpgen)
        await test_charts(lpgen)


if __name__ == "__main__":
    setup_logs(logging.INFO)
    # asyncio.run(show_me_example_liquidity())
    asyncio.run(main())
