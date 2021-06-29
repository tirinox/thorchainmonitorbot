import asyncio
import logging
import os

from services.dialog.picture.lp_picture import lp_pool_picture, lp_address_summary_picture
from services.jobs.fetch.runeyield.lp_my import HomebrewLPConnector
from services.lib.utils import load_pickle, save_pickle
from tools.lib.lp_common import LpAppFramework, LpGenerator

CACHE_REPORTS = False  # fixme!

TOKEN_KYL = 'ETH.KYL-0X67B6D479C7BB412C54E03DCA8E1BC6740CE6B99C'


async def test_one_pool_picture_generator(addr, pool, hide, rune_yield_class=HomebrewLPConnector):
    stake_report_path = f'../../tmp/stake_report_{addr}.pickle'
    stake_picture_path = f'../../tmp/stake_test_{addr}.png'

    lpgen = LpGenerator(rune_yield_class)

    stake_report = load_pickle(stake_report_path) if CACHE_REPORTS else None

    if not stake_report:
        async with lpgen:
            stake_report = await lpgen.get_report(addr, pool)
            save_pickle(stake_report_path, stake_report)

    img = await lp_pool_picture(stake_report, lpgen.deps.loc_man.default, value_hidden=hide)
    img.save(stake_picture_path, "PNG")
    os.system(f'open "{stake_picture_path}"')


async def test_summary_picture_generator(addr, hide, rune_yield_class=HomebrewLPConnector):
    stake_summary_path = f'../../tmp/stake_report_summary_{addr}.pickle'
    stake_picture_path = f'../../tmp/stake_test_summary_{addr}.png'

    lpgen = LpGenerator(rune_yield_class)

    data = load_pickle(stake_summary_path) if CACHE_REPORTS else None

    if data:
        stakes, charts = data
    else:
        async with lpgen:
            stakes, charts = await lpgen.test_summary(addr)
        save_pickle(stake_summary_path, (stakes, charts))

    img = await lp_address_summary_picture(stakes, charts, lpgen.deps.loc_man.default, value_hidden=hide)
    img.save(stake_picture_path, "PNG")
    os.system(f'open "{stake_picture_path}"')


async def test_single_chain_chaosnet():
    g1 = test_summary_picture_generator('bnb157zacwqaplw5kdwpkrve6n2jdxu3ps9cj3xdcp', hide=False)
    # g2 = test_one_pool_picture_generator('bnb1rv89nkw2x5ksvhf6jtqwqpke4qhh7jmudpvqmj', pool=BNB_BTCB_SYMBOL,
    #                                      hide=False)

    await g1


async def test_my_pools():
    lpgen = LpAppFramework(HomebrewLPConnector)
    async with lpgen:
        my_pools = await lpgen.rune_yield.get_my_pools('tthor1cwcqhhjhwe8vvyn8vkufzyg0tt38yjgzdf9whh')

        print(my_pools)

        if hasattr(lpgen.rune_yield, 'get_compound_addresses'):
            comp_addr = await lpgen.rune_yield.get_compound_addresses('tthor1cwcqhhjhwe8vvyn8vkufzyg0tt38yjgzdf9whh')
            print(comp_addr)


async def test_multi_chain_testnet():
    # todo: 1) test for address with no IL coverage

    # await test_one_pool_picture_generator('thor1zaphk0dm3v3kucla7a4hlh05hsdhwqdfdjqadg', 'BNB.BNB', hide=False)
    # fixme: APY!

    # 2) test for address with IL coverage added to final numbers

    # this has + and -
    # await test_one_pool_picture_generator('bnb13njdl8ktw7pen3jcjy7epfa3mzcdjxuu3w4dxh', 'BNB.BNB', hide=False)
    await test_one_pool_picture_generator('bnb1rpw69vck9txkql2hw8t80uxdapve0rlw6ywkhf', 'BNB.BUSD-BD1', hide=False)
    # fixme: last tx? withdraw 10000? all??

    # ----------------

    # 5 TX, No IL protection needed!
    # https://app.runeyield.info/dashboard?eth=0x5d11b2491ec1673402de8ee85f0076ba4c27d1a1
    # await test_one_pool_picture_generator('0x5d11b2491ec1673402de8ee85f0076ba4c27d1a1', 'ETH.ETH', hide=False)

    # ----------------

    # todo! eth tokens test fee > 0!
    # https://app.runeyield.info/dashboard?eth=0x5d11b2491ec1673402de8ee85f0076ba4c27d1a1
    # 0x5d11b2491ec1673402de8ee85f0076ba4c27d1a1
    # await test_one_pool_picture_generator('0x5d11b2491ec1673402de8ee85f0076ba4c27d1a1', TOKEN_KYL, hide=False)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(test_multi_chain_testnet())
