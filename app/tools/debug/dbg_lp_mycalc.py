import asyncio
from datetime import date

from services.dialog.picture.lp_picture import lp_pool_picture
from services.jobs.fetch.runeyield.date2block import DateToBlockMapper
from services.jobs.fetch.runeyield.lp_my import HomebrewLPConnector
from services.jobs.fetch.tx import TxFetcher
from tools.lib.lp_common import LpAppFramework


async def my_test_get_user_lp_actions(lpgen: LpAppFramework):
    txf = TxFetcher(lpgen.deps)
    res = await txf.fetch_all_tx('tthor1qtedshax98p3v9al3pqjrfmf32xmrlfzs7lxg2', liquidity_change_only=True)
    for tx in res:
        print(tx, end='\n-----\n')


ADDR = 'thor1a8ydprhkk5u032r277nzs4vw5khnnl3ya9xnvs'
POOL = 'ETH.ETH'


# POOL = 'BNB.TWT-8C2'
# POOL = 'BNB.BTCB-1DE'
# POOL = 'BNB.BUSD-BD1'


async def my_test_summary_of_all_pools(lpgen: LpAppFramework):
    pools = await lpgen.rune_yield.get_my_pools(ADDR)
    yield_report = await lpgen.rune_yield.generate_yield_summary(ADDR, pools)
    for r in yield_report.reports:
        print(r.fees)
        print('------')


async def my_test_1_pool(lpgen: LpAppFramework):
    report = await lpgen.rune_yield.generate_yield_report_single_pool(ADDR, POOL)
    print(report)

    loc = lpgen.deps.loc_man.default
    picture = await lp_pool_picture(lpgen.deps.price_holder, report, loc)
    picture.show()


async def my_test_block_calibration(lpgen: LpAppFramework):
    dbm = DateToBlockMapper(lpgen.deps)
    blocks = await dbm.calibrate(14, overwrite=True)
    print('-' * 100)
    print(blocks)
    # date_of_interest = datetime.now() - timedelta(days=1)
    # r = await dbm.iterative_block_discovery_by_timestamp(date_of_interest.timestamp())
    # print(r)


async def my_test_block_by_date(lpgen: LpAppFramework):
    dbm = DateToBlockMapper(lpgen.deps)
    d = date(2022, 10, 13)

    last_block = await dbm.get_last_thorchain_block()
    r = await dbm.get_block_height_by_date(d, last_block)
    print(r)


async def clear_date2block(lpgen: LpAppFramework):
    dbm = DateToBlockMapper(lpgen.deps)
    await dbm.clear()


async def main():
    lpgen = LpAppFramework(HomebrewLPConnector)
    async with lpgen:
        await my_test_1_pool(lpgen)
        # await test_block_calibration(lpgen)
        # await clear_date2block(lpgen)
        # await my_test_block_by_date(lpgen)


if __name__ == "__main__":
    asyncio.run(main())
