import asyncio
import logging
import os
import pickle
from time import time

import aiohttp

from services.dialog.lp_picture import lp_pool_picture
from services.fetch.lp import LiqPoolFetcher
from services.fetch.node_ip_manager import ThorNodeAddressManager
from services.fetch.pool_price import PoolPriceFetcher
from services.lib.config import Config
from services.lib.datetime import DAY
from services.lib.db import DB
from services.lib.depcont import DepContainer
from services.models.stake_info import BNB_CHAIN, StakePoolReport, CurrentLiquidity
from services.models.time_series import BNB_SYMBOL, RUNE_SYMBOL, BUSD_SYMBOL, BTCB_SYMBOL


async def price_of_day(d: DepContainer):
    async with aiohttp.ClientSession() as d.session:
        lpf = LiqPoolFetcher(d)
        ppf = PoolPriceFetcher(d)
        d.thor_man = ThorNodeAddressManager(d.session)

        r = await ppf.get_usd_per_rune_asset_per_rune_by_day(BTCB_SYMBOL, time() - 2 * DAY)
        print(r)


async def lp_test(d: DepContainer, addr):
    async with aiohttp.ClientSession() as d.session:
        lpf = LiqPoolFetcher(d)
        ppf = PoolPriceFetcher(d)
        d.thor_man = ThorNodeAddressManager(d.session)
        await ppf.get_current_pool_data_full()

        cur_liqs = await lpf.fetch_liquidity_info(addr)

        cur_liq: CurrentLiquidity = cur_liqs[BTCB_SYMBOL]

        stake_report = await lpf.fetch_stake_report_for_pool(cur_liq, ppf)

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


PICKLE_PATH = '../../stake_report.pickle'


async def test_image(d, addr, hide):
    if os.path.exists(PICKLE_PATH):
        with open(PICKLE_PATH, 'rb') as f:
            stake_report = pickle.load(f)
    else:
        stake_report = await lp_test(d, addr)
        with open(PICKLE_PATH, 'wb') as f:
            pickle.dump(stake_report, f)

    # stake_report = await lp_test(d, addr)

    img = await lp_pool_picture(stake_report, value_hidden=hide)
    img.save("../../stake_test.png", "PNG")

    # await price_of_day(d)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    d = DepContainer()
    d.loop = asyncio.get_event_loop()
    d.cfg = Config(Config.DEFAULT_LVL_UP)
    d.db = DB(d.loop)

    d.loop.run_until_complete(test_image(d, 'bnb1rv89nkw2x5ksvhf6jtqwqpke4qhh7jmudpvqmj', hide=True))
