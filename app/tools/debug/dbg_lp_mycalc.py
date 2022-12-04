import asyncio
import logging
from datetime import date

from localization.languages import Language
from services.dialog.picture.lp_picture import generate_yield_picture, savings_pool_picture, lp_address_summary_picture
from services.jobs.fetch.runeyield.date2block import DateToBlockMapper
from services.jobs.fetch.runeyield.lp_my import HomebrewLPConnector
from services.jobs.fetch.tx import TxFetcher
from services.lib.money import Asset
from services.lib.texts import sep
from services.models.tx import cut_off_previous_lp_sessions
from tools.lib.lp_common import LpAppFramework

LANG = Language.RUSSIAN


async def my_test_get_user_lp_actions(lpgen: LpAppFramework):
    txf = TxFetcher(lpgen.deps)
    res = await txf.fetch_all_tx('tthor1qtedshax98p3v9al3pqjrfmf32xmrlfzs7lxg2', liquidity_change_only=True)
    for tx in res:
        print(tx, end='\n-----\n')


async def my_test_summary_of_all_pools(lpgen: LpAppFramework, addr):
    pools = await lpgen.rune_yield.get_my_pools(addr)
    yield_report = await lpgen.rune_yield.generate_yield_summary(addr, pools)
    for r in yield_report.reports:
        print(r.fees)
        print('------')


async def demo_report_for_single_pool(lpgen: LpAppFramework, addr, pool, hidden=True):
    is_savers = Asset.from_string(pool).is_synth
    sep()
    print(f'{addr = }, {pool = }, {is_savers = }')
    sep()

    loc = lpgen.deps.loc_man[LANG]
    report = await lpgen.rune_yield.generate_yield_report_single_pool(addr, pool)
    print(report)
    if is_savers:
        picture = await savings_pool_picture(lpgen.deps.price_holder, report, loc, hidden)
    else:
        picture = await generate_yield_picture(lpgen.deps.price_holder, report, loc, hidden)
    picture.show()


async def demo_summary_all_pools(lpgen: LpAppFramework, addr, hidden=False):
    loc = lpgen.deps.loc_man[LANG]
    lpgen.rune_yield.add_il_protection_to_final_figures = True
    pools = await lpgen.rune_yield.get_my_pools(addr, show_savers=True)
    print(f'{addr} has {pools = }')
    yield_summary = await lpgen.rune_yield.generate_yield_summary(addr, pools)

    # GENERATE A PICTURE
    picture = await lp_address_summary_picture(list(yield_summary.reports),
                                               yield_summary.charts,
                                               loc, value_hidden=hidden)
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


async def demo_get_my_pools(app: LpAppFramework, address):
    pools = await app.rune_yield.get_my_pools(address, show_savers=True)
    print(f'{address = } => {pools = }')


async def get_members_for_saving_pool(app: LpAppFramework, pool: str):
    assert '/' in pool
    return await app.deps.midgard_connector.request(f'v2/members?pool={pool}')


async def get_savers_txs(app: LpAppFramework, pool, member):
    txs = await app.rune_yield.tx_fetcher.fetch_all_tx(member, liquidity_change_only=True)
    txs = [tx for tx in txs if pool == tx.first_pool]
    return txs


async def demo_find_interesting_savers(app: LpAppFramework):
    savers_pools = ['ETH/ETH', 'BTC/BTC', 'BNB/BNB', 'LTC/LTC']
    for pool in savers_pools:
        members = await get_members_for_saving_pool(app, pool)
        print(f'{pool = }; {len(members) = }')
        for i, member in enumerate(members, start=1):
            txs = await get_savers_txs(app, pool, member)
            n = len(txs)
            exclamation = '!' * min(10, n // 3)
            print(f'[{i:4}/{len(members):4}]{pool = } and {member =} =>> has {n} savings txs {exclamation}')

            if (n_this_session := len(cut_off_previous_lp_sessions(txs))) != n:
                print(f'interrupted sessions detected: {n_this_session = } but {n = } !!!')


async def main():
    app = LpAppFramework(HomebrewLPConnector, log_level=logging.INFO)
    async with app:
        global LANG
        LANG = Language.ENGLISH
        # await demo_find_interesting_savers(app)
        # await demo_get_my_pools(app, 'bc1q0jmh2ht08zha0vajx0kq87vxtyspak45xywf2p')
        # await demo_report_for_single_pool(app, 'thor1a8ydprhkk5u032r277nzs4vw5khnnl3ya9xnvs', 'ETH.ETH')
        # await demo_report_for_single_pool(app, 'bc1q0jmh2ht08zha0vajx0kq87vxtyspak45xywf2p', 'BTC/BTC')  # only 1 add

        # many a/w, small
        # await demo_report_for_single_pool(app, '0x8745be2c582bcfc50acf9d2c61caded65a4e3825', 'ETH/ETH')

        # interrupted
        # await demo_report_for_single_pool(app, '0xe93b5b56bddccaab6d396b7d4058f50acd4ae5d0', 'ETH/ETH')

        # 11 add?
        # await demo_report_for_single_pool(app, 'bc1qcsmgsvfpp4w6dmlwwdf4s87ngh8trz8yuwsfy0', 'BTC/BTC', hidden=False)

        # interrupted
        # await demo_report_for_single_pool(app, 'ltc1q67tf8ryuggvetakwz5flex5ydhyvn7rp0y8kx3', 'LTC/LTC', hidden=False)

        # await test_block_calibration(app)
        # await clear_date2block(app)
        # await my_test_block_by_date(app)

        # await demo_summary_all_pools(app, 'thor1gzautydm2mrpcuj36drqyzuuzqw4w8cp8zjj2c')  # 3 classic LP
        await demo_summary_all_pools(app, 'bc1qcsmgsvfpp4w6dmlwwdf4s87ngh8trz8yuwsfy0')  # savers


if __name__ == "__main__":
    asyncio.run(main())
