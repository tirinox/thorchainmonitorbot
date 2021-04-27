import asyncio
import logging
from datetime import datetime, timedelta, date

from services.jobs.fetch.runeyield import AsgardConsumerConnectorV1
from services.jobs.fetch.runeyield.date2block import DateToBlockMapper
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

    data_path = f'../../lp_chart_data-{address}.pickle'

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

    day_units = await rl._get_charts(user_txs, days=14)
    print(day_units)


async def test_block_calibration(lpgen: LpTesterBase):
    dbm = DateToBlockMapper(lpgen.deps)
    blocks = await dbm.calibrate(14, overwrite=True)
    print('-' * 100)
    print(blocks)
    # date_of_interest = datetime.now() - timedelta(days=1)
    # r = await dbm.iterative_block_discovery_by_timestamp(date_of_interest.timestamp())
    # print(r)


async def test_block_by_date(lpgen: LpTesterBase):
    dbm = DateToBlockMapper(lpgen.deps)
    d = date(2021, 4, 13)

    last_block = await dbm.get_last_thorchain_block()
    r = await dbm.get_block_height_by_date(d, last_block)
    print(r)


async def clear_date2block(lpgen: LpTesterBase):
    dbm = DateToBlockMapper(lpgen.deps)
    await dbm.clear()


async def main():
    lpgen = LpTesterBase(HomebrewLPConnector)
    async with lpgen:
        # await test_1_pool(lpgen)
        # await test_charts(lpgen, address='bnb1snqqjdvcqjf76fdztxrtwgv0ws9hsvvfsjv02z')  # mccn (bnb only)
        await test_charts(lpgen, address='0x52e07b963ab0f525b15e281b3b42d55e8048f027')  # mccn (many pools + withdraw)
        # await test_block_calibration(lpgen)
        # await test_block_by_date(lpgen)


if __name__ == "__main__":
    setup_logs(logging.INFO)
    # asyncio.run(show_me_example_liquidity())
    asyncio.run(main())
