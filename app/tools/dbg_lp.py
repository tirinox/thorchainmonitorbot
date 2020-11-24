import asyncio
import logging
import os
import pickle

import aiohttp

from services.dialog.lp_picture import lp_pool_picture, download_logo_cached
from services.fetch.lp import LiqPoolFetcher
from services.fetch.node_ip_manager import ThorNodeAddressManager
from services.fetch.pool_price import PoolPriceFetcher
from services.lib.config import Config
from services.lib.db import DB
from services.lib.depcont import DepContainer
from services.models.stake_info import BNB_CHAIN, StakePoolReport, CurrentLiquidity
from services.models.time_series import BNB_SYMBOL, RUNE_SYMBOL, BUSD_SYMBOL


async def lp_test(d: DepContainer, addr):
    async with aiohttp.ClientSession() as d.session:
        lpf = LiqPoolFetcher(d)
        ppf = PoolPriceFetcher(d)
        d.thor_man = ThorNodeAddressManager(d.session)
        await ppf.get_current_pool_data_full()

        cur_liqs = await lpf.fetch(addr, BNB_CHAIN)
        cur_liq: CurrentLiquidity = cur_liqs['BNB.BNB']

        stake_report = StakePoolReport(d.price_holder.usd_per_asset(cur_liq.pool),
                                       d.price_holder.usd_per_rune,
                                       cur_liq,
                                       d.price_holder.pool_info_map.get(cur_liq.pool))
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


async def test_image(d, addr):
    if os.path.exists(PICKLE_PATH):
        with open(PICKLE_PATH, 'rb') as f:
            stake_report = pickle.load(f)
    else:
        stake_report = await lp_test(d, addr)
        with open(PICKLE_PATH, 'wb') as f:
            pickle.dump(stake_report, f)

    img = await lp_pool_picture(stake_report)
    img.save("../../stake_test.png", "PNG")



if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    d = DepContainer()
    d.loop = asyncio.get_event_loop()
    d.cfg = Config(Config.DEFAULT_LVL_UP)
    d.db = DB(d.loop)

    d.loop.run_until_complete(test_image(d, 'bnb1rv89nkw2x5ksvhf6jtqwqpke4qhh7jmudpvqmj'))
