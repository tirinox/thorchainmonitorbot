import asyncio

import aiohttp
from aiothornode.connector import ThorConnector

from localization import LocalizationManager
from services.lib.constants import get_thor_env_by_network_id
from services.jobs.fetch.const_mimir import ConstMimirFetcher
from services.jobs.fetch.pool_price import PoolPriceFetcher
from services.jobs.fetch.runeyield import AsgardConsumerConnectorBase, get_rune_yield_connector
from services.lib.config import Config
from services.lib.db import DB
from services.lib.depcont import DepContainer
from services.lib.midgard.urlgen import get_url_gen_by_network_id
from services.lib.telegram import telegram_send_message_basic, TG_TEST_USER


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
        self.deps.price_pool_fetcher = PoolPriceFetcher(d)
        self.deps.mimir_const_holder = ConstMimirFetcher(d)

    @property
    def tg_token(self):
        return self.deps.cfg.get('telegram.bot.token')

    async def send_test_tg_message(self, txt, **kwargs):
        return await telegram_send_message_basic(self.tg_token, TG_TEST_USER, txt, **kwargs)

    async def prepare(self, brief=False):
        d = self.deps
        d.session = aiohttp.ClientSession()
        d.thor_connector = ThorConnector(get_thor_env_by_network_id(d.cfg.network_id), d.session)

        await d.db.get_redis()

        if brief:
            return

        d.mimir_const_holder = ConstMimirFetcher(d)
        await d.mimir_const_holder.fetch()  # get constants beforehand

        d.price_pool_fetcher = PoolPriceFetcher(d)

        if self.rune_yield_class:
            self.rune_yield = self.rune_yield_class(d, get_url_gen_by_network_id(self.deps.cfg.network_id))
        else:
            self.rune_yield = get_rune_yield_connector(d)

        await d.price_pool_fetcher.fetch()

    async def close(self):
        await self.deps.session.close()

    async def __aenter__(self):
        await self.prepare()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


class LpGenerator(LpAppFramework):
    async def get_report(self, addr, pool):
        lp_report = await self.rune_yield.generate_yield_report_single_pool(addr, pool)

        # -------- print out ----------
        redeem_rune, redeem_asset = lp_report.redeemable_rune_asset
        print(f'redeem_rune = {redeem_rune} and redeem_asset = {redeem_asset}')
        print()
        USD, ASSET, RUNE = lp_report.USD, lp_report.ASSET, lp_report.RUNE
        print(f'current_value(USD) = {lp_report.current_value(USD)}')
        print(f'current_value(ASSET) = {lp_report.current_value(ASSET)}')
        print(f'current_value(RUNE) = {lp_report.current_value(RUNE)}')
        print()
        gl_usd, gl_usd_p = lp_report.gain_loss(USD)
        gl_ass, gl_ass_p = lp_report.gain_loss(ASSET)
        gl_rune, gl_rune_p = lp_report.gain_loss(RUNE)
        print(f'gain/loss(USD) = {gl_usd}, {gl_usd_p:.1f} %')
        print(f'gain/loss(ASSET) = {gl_ass}, {gl_ass_p:.1f} %')
        print(f'gain/loss(RUNE) = {gl_rune}, {gl_rune_p:.1f} %')
        print()
        lp_abs, lp_per = lp_report.lp_vs_hold
        apy = lp_report.lp_vs_hold_apy
        print(f'lp_report.lp_vs_hold = {lp_abs}, {lp_per:.1f} %')
        print(f'lp_report.lp_vs_hold_apy = {apy}')

        return lp_report

    async def test_summary(self, address):
        lp_reports, weekly_charts = await self.rune_yield.generate_yield_summary(address, [])
        return lp_reports, weekly_charts
