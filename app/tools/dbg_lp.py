import asyncio
import logging
import os
import pickle
from time import time

import aiohttp

from localization import LocalizationManager, RussianLocalization
from services.dialog.lp_picture import lp_pool_picture, lp_address_summary_picture
from services.fetch.lp import LiqPoolFetcher
from services.fetch.node_ip_manager import ThorNodeAddressManager
from services.fetch.pool_price import PoolPriceFetcher
from services.lib.config import Config
from services.lib.datetime import DAY
from services.lib.db import DB
from services.lib.depcont import DepContainer
from services.models.stake_info import CurrentLiquidity
from services.models.time_series import BTCB_SYMBOL


async def load_one_pool_liquidity(d: DepContainer, addr, pool=BTCB_SYMBOL):
    async with aiohttp.ClientSession() as d.session:
        await d.db.get_redis()
        lpf = LiqPoolFetcher(d)
        ppf = PoolPriceFetcher(d)
        d.thor_man = ThorNodeAddressManager(d.cfg.thornode.seed, d.session)
        await ppf.get_current_pool_data_full()

        cur_liqs = await lpf.fetch_all_pool_liquidity_info(addr)

        cur_liq: CurrentLiquidity = cur_liqs[pool]

        stake_report = await lpf.fetch_stake_report_for_pool(cur_liq, ppf)

        # -------- print out ----------

        print(f'cur_liq = {cur_liq}')
        print()
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
        d.thor_man.session = d.session
        lpf = LiqPoolFetcher(d)
        ppf = PoolPriceFetcher(d)
        await ppf.get_current_pool_data_full()
        liqs = await lpf.fetch_all_pool_liquidity_info(address)
        pools = list(liqs.keys())
        liqs = list(liqs.values())
        weekly_charts = await lpf.fetch_all_pools_weekly_charts(address, pools)
        stake_reports = await asyncio.gather(*[lpf.fetch_stake_report_for_pool(liq, ppf) for liq in liqs])
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

    img = await lp_address_summary_picture(stakes, charts, RussianLocalization(), value_hidden=hide)
    img.save(PICTURE_PATH, "PNG")
    os.system(f'open "{PICTURE_PATH}"')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    d = DepContainer()
    d.loop = asyncio.get_event_loop()
    d.cfg = Config()
    d.loc_man = LocalizationManager()
    d.thor_man = ThorNodeAddressManager(d.cfg.thornode.seed)
    d.db = DB(d.loop)

    # d.loop.run_until_complete(
    #     test_one_pool_picture_generator(d,
    #                                     'bnb1rv89nkw2x5ksvhf6jtqwqpke4qhh7jmudpvqmj',
    #                                     pool=BTCB_SYMBOL,
    #                                     hide=True))

    d.loop.run_until_complete(
        test_summary_picture_generator(d,
                                       'bnb157zacwqaplw5kdwpkrve6n2jdxu3ps9cj3xdcp',
                                       hide=False))  # bnb1rv89nkw2x5ksvhf6jtqwqpke4qhh7jmudpvqmj
