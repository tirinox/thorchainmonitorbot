import asyncio
import logging
import os
import pickle

import aiohttp
from aiothornode.connector import ThorConnector

from localization import LocalizationManager, RussianLocalization
from main import get_thor_env_by_network_id
from services.dialog.picture.lp_picture import lp_pool_picture, lp_address_summary_picture
from services.jobs.fetch.pool_price import PoolPriceFetcher
from services.jobs.fetch.runeyield import get_rune_yield_connector, AsgardConsumerConnectorBase
from services.lib.midgard.urlgen import get_url_gen_by_network_id
from services.lib.config import Config
from services.lib.constants import BNB_BTCB_SYMBOL
from services.lib.db import DB
from services.lib.depcont import DepContainer

CACHE_REPORTS = False


class LpTesterBase:
    def __init__(self, rune_yield_class=None) -> None:
        d = DepContainer()
        d.loop = asyncio.get_event_loop()
        d.cfg = Config()
        d.loc_man = LocalizationManager(d.cfg)
        d.db = DB(d.loop)
        self.deps = d
        self.rune_yield: AsgardConsumerConnectorBase
        self.rune_yield_class = rune_yield_class
        self.ppf = PoolPriceFetcher(d)

    async def prepare(self):
        d = self.deps
        d.session = aiohttp.ClientSession()
        await d.db.get_redis()
        self.ppf = PoolPriceFetcher(d)
        if self.rune_yield_class:
            self.rune_yield = self.rune_yield_class(d, self.ppf, get_url_gen_by_network_id(self.deps.cfg.network_id))
        else:
            self.rune_yield = get_rune_yield_connector(d, self.ppf)
        d.thor_connector = ThorConnector(get_thor_env_by_network_id(d.cfg.network_id), d.session)
        await self.ppf.fetch()

    async def close(self):
        await self.deps.session.close()

    async def __aenter__(self):
        await self.prepare()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


class LpGenerator(LpTesterBase):
    async def get_report(self, addr, pool):
        stake_report = await self.rune_yield.generate_yield_report_single_pool(addr, pool)

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

    async def test_summary(self, address):
        stake_reports, weekly_charts = await self.rune_yield.generate_yield_summary(address, [])
        return stake_reports, weekly_charts

    async def get_lp_position(self, asset, my_stake_units):
        pool_info = self.deps.price_holder.find_pool(asset)
        if pool_info:
            return pool_info.create_lp_position(my_stake_units, self.deps.price_holder.usd_per_rune)


async def test_one_pool_picture_generator(addr, pool, hide):
    PICKLE_PATH = '../../stake_report.pickle'
    PICTURE_PATH = '../../stake_test.png'

    lpgen = LpGenerator()

    if CACHE_REPORTS and os.path.exists(PICKLE_PATH):
        with open(PICKLE_PATH, 'rb') as f:
            stake_report = pickle.load(f)
    else:
        async with lpgen:
            stake_report = await lpgen.get_report(addr, pool)
            with open(PICKLE_PATH, 'wb') as f:
                pickle.dump(stake_report, f)

    img = await lp_pool_picture(stake_report, lpgen.deps.loc_man.default, value_hidden=hide)
    img.save(PICTURE_PATH, "PNG")
    os.system(f'open "{PICTURE_PATH}"')


async def test_summary_picture_generator(addr, hide):
    PICKLE_PATH = '../../stake_report_summary.pickle'
    PICTURE_PATH = '../../stake_test_summary.png'

    lpgen = LpGenerator()

    if CACHE_REPORTS and os.path.exists(PICKLE_PATH):
        with open(PICKLE_PATH, 'rb') as f:
            stakes, charts = pickle.load(f)
    else:
        async with lpgen:
            stakes, charts = await lpgen.test_summary(addr)

        with open(PICKLE_PATH, 'wb') as f:
            pickle.dump((stakes, charts), f)

    img = await lp_address_summary_picture(stakes, charts, lpgen.deps.loc_man.default, value_hidden=hide)
    img.save(PICTURE_PATH, "PNG")
    os.system(f'open "{PICTURE_PATH}"')


async def test_single_chain_chaosnet():
    g1 = test_summary_picture_generator('bnb157zacwqaplw5kdwpkrve6n2jdxu3ps9cj3xdcp', hide=False)
    g2 = test_one_pool_picture_generator('bnb1rv89nkw2x5ksvhf6jtqwqpke4qhh7jmudpvqmj', pool=BNB_BTCB_SYMBOL,
                                         hide=False)

    await g1


async def test_my_pools():
    lpgen = LpTesterBase()
    async with lpgen:
        my_pools = await lpgen.rune_yield.get_my_pools('tthor1cwcqhhjhwe8vvyn8vkufzyg0tt38yjgzdf9whh')

        print(my_pools)

        if hasattr(lpgen.rune_yield, 'get_compound_addresses'):
            comp_addr = await lpgen.rune_yield.get_compound_addresses('tthor1cwcqhhjhwe8vvyn8vkufzyg0tt38yjgzdf9whh')
            print(comp_addr)


async def test_lp_position():
    lpgen = LpGenerator()
    async with lpgen:
        print(await lpgen.get_lp_position('BTC.BTC', 0.1))


async def test_multi_chain_testnet():
    # await test_my_pools()
    # MCTN
    # await test_one_pool_picture_generator('tthor1cwcqhhjhwe8vvyn8vkufzyg0tt38yjgzdf9whh', 'BTC.BTC', hide=False)
    # await test_one_pool_picture_generator('bnb1sa4hx03jrcg44ktmxuxu5g2jj8u6rln063kx9l', 'BNB.USDT-6D8', hide=False)  # BEP2

    # await test_summary_picture_generator('tthor1vyp3y7pjuwsz2hpkwrwrrvemcn7t758sfs0glr', hide=False)
    await test_lp_position()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(test_multi_chain_testnet())
