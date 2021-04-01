import asyncio
import logging
import os
import pickle

import aiohttp
from aiothornode.connector import ThorConnector, TEST_NET_ENVIRONMENT_MULTI_1

from localization import LocalizationManager, RussianLocalization
from main import get_thor_env_by_network_id
from services.dialog.picture.lp_picture import lp_pool_picture, lp_address_summary_picture
from services.jobs.fetch.pool_price import PoolPriceFetcher
from services.jobs.fetch.runeyield import get_rune_yield_connector
from services.lib.config import Config
from services.lib.constants import BNB_BTCB_SYMBOL
from services.lib.db import DB
from services.lib.depcont import DepContainer


async def load_one_pool_liquidity(d: DepContainer, addr, pool=BNB_BTCB_SYMBOL):
    async with aiohttp.ClientSession() as d.session:
        await d.db.get_redis()
        ppf = PoolPriceFetcher(d)
        rune_yield = get_rune_yield_connector(d, ppf)
        d.thor_connector = ThorConnector(get_thor_env_by_network_id(d.cfg.network_id), d.session)
        await ppf.get_current_pool_data_full()

        stake_report = await rune_yield.generate_yield_report_single_pool(addr, pool)

        # -------- print out ----------

        redeem_rune, redeem_asset = stake_report.redeemable_rune_asset
        print(f'redeem_rune = {redeem_rune} and redeem_asset = {redeem_asset}')
        print()
        USD, ASSET, RUNE = stake_report.USD, stake_report.ASSET, stake_report.RUNE
        print(f'current_value(USD) = {stake_report.current_value(USD)}')
        print(f'current_value(ASSET) = {stake_report.current_value(ASSET)}')
        print(f'current_value(RUNE) = {stake_report.current_value(RUNE)}')
        print()
        gl_usd, gl_usd_p = stake_report.gain_loss(USD)
        gl_ass, gl_ass_p = stake_report.gain_loss(ASSET)
        gl_rune, gl_rune_p = stake_report.gain_loss(RUNE)
        print(f'gain/loss(USD) = {gl_usd}, {gl_usd_p:.1f} %')
        print(f'gain/loss(ASSET) = {gl_ass}, {gl_ass_p:.1f} %')
        print(f'gain/loss(RUNE) = {gl_rune}, {gl_rune_p:.1f} %')
        print()
        lp_abs, lp_per = stake_report.lp_vs_hold
        apy = stake_report.lp_vs_hold_apy
        print(f'stake_report.lp_vs_hold = {lp_abs}, {lp_per:.1f} %')
        print(f'stake_report.lp_vs_hold_apy = {apy}')

        return stake_report


async def load_summary_for_address(d: DepContainer, address):
    async with aiohttp.ClientSession() as d.session:
        await d.db.get_redis()
        d.thor_connector = ThorConnector(get_thor_env_by_network_id(d.cfg.network_id), d.session)
        ppf = PoolPriceFetcher(d)
        rune_yield = get_rune_yield_connector(d, ppf)
        await ppf.get_current_pool_data_full()

        stake_reports, weekly_charts = await rune_yield.generate_yield_summary(address, [])
        return stake_reports, weekly_charts


async def test_one_pool_picture_generator(d: DepContainer, addr, pool, hide):
    PICKLE_PATH = '../../stake_report.pickle'
    PICTURE_PATH = '../../stake_test.png'

    if os.path.exists(PICKLE_PATH):
        with open(PICKLE_PATH, 'rb') as f:
            stake_report = pickle.load(f)
    else:
        stake_report = await load_one_pool_liquidity(d, addr, pool)
        with open(PICKLE_PATH, 'wb') as f:
            pickle.dump(stake_report, f)

    img = await lp_pool_picture(stake_report, d.loc_man.default, value_hidden=hide)
    img.save(PICTURE_PATH, "PNG")
    os.system(f'open "{PICTURE_PATH}"')


async def test_summary_picture_generator(d: DepContainer, addr, hide):
    PICKLE_PATH = '../../stake_report_summary.pickle'
    PICTURE_PATH = '../../stake_test_summary.png'

    if os.path.exists(PICKLE_PATH):
        with open(PICKLE_PATH, 'rb') as f:
            stakes, charts = pickle.load(f)
    else:
        stakes, charts = await load_summary_for_address(d, addr)
        with open(PICKLE_PATH, 'wb') as f:
            pickle.dump((stakes, charts), f)

    # stakes = await load_summary_for_address(d, addr)  # direct load

    img = await lp_address_summary_picture(stakes, charts, RussianLocalization(d.cfg), value_hidden=hide)
    img.save(PICTURE_PATH, "PNG")
    os.system(f'open "{PICTURE_PATH}"')


async def test_single_chain_chaosnet(d: DepContainer):
    g1 = test_summary_picture_generator(d, 'bnb157zacwqaplw5kdwpkrve6n2jdxu3ps9cj3xdcp', hide=False)
    g2 = test_one_pool_picture_generator(d, 'bnb1rv89nkw2x5ksvhf6jtqwqpke4qhh7jmudpvqmj', pool=BNB_BTCB_SYMBOL,
                                         hide=False)

    await g1


async def test_multi_chain_testet(d: DepContainer):
    # await test_one_pool_picture_generator(d, 'tthor1cwcqhhjhwe8vvyn8vkufzyg0tt38yjgzdf9whh', 'BTC.BTC', hide=False)

    await test_summary_picture_generator(d, 'tthor1vyp3y7pjuwsz2hpkwrwrrvemcn7t758sfs0glr', hide=False)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    d = DepContainer()
    d.loop = asyncio.get_event_loop()
    d.cfg = Config()
    d.loc_man = LocalizationManager(d.cfg)
    d.db = DB(d.loop)

    d.loop.run_until_complete(test_multi_chain_testet(d))
    # d.loop.run_until_complete(test_single_chain_chaosnet())
