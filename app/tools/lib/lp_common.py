import asyncio

import aiohttp
from aiothornode.connector import ThorConnector

from localization import LocalizationManager
from main import get_thor_env_by_network_id
from services.jobs.fetch.pool_price import PoolPriceFetcher
from services.jobs.fetch.runeyield import AsgardConsumerConnectorBase, get_rune_yield_connector
from services.lib.config import Config
from services.lib.db import DB
from services.lib.depcont import DepContainer
from services.lib.midgard.urlgen import get_url_gen_by_network_id


class LpAppFramework:
    def __init__(self, rune_yield_class=None, network=None) -> None:
        d = DepContainer()
        d.loop = asyncio.get_event_loop()
        d.cfg = Config()
        if network:
            d.cfg.network_id = network
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


class LpGenerator(LpAppFramework):
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
