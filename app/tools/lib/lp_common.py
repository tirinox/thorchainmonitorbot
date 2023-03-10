import logging
import os

from main import App
from services.dialog.telegram.telegram import telegram_send_message_basic, TG_TEST_USER
from services.dialog.twitter.twitter_bot import TwitterBotMock
from services.jobs.fetch.fair_price import RuneMarketInfoFetcher
from services.jobs.fetch.last_block import LastBlockFetcher
from services.jobs.fetch.runeyield import AsgardConsumerConnectorBase, get_rune_yield_connector
from services.jobs.fetch.tx import TxFetcher
from services.lib.constants import NetworkIdents
from services.lib.delegates import INotified
from services.lib.draw_utils import img_to_bio
from services.lib.midgard.parser import MidgardParserV2
from services.lib.texts import sep
from services.lib.utils import load_json
from services.notify.types.block_notify import LastBlockStore


class LpAppFramework(App):
    def __init__(self, rune_yield_class=None, network=None, log_level=logging.DEBUG) -> None:
        self.solve_working_dir_mess()  # first of all!

        super().__init__(log_level)
        self.brief = None

        d = self.deps

        if network:
            d.cfg.network_id = network

        d.loc_man.set_name_service(d.name_service)
        d.twitter_bot = TwitterBotMock(d.cfg)
        d.last_block_fetcher = LastBlockFetcher(d)
        d.last_block_store = LastBlockStore(d)

        self.rune_yield: AsgardConsumerConnectorBase
        self.rune_yield_class = rune_yield_class

        if self.rune_yield_class:
            self.rune_yield = self.rune_yield_class(d)
        else:
            self.rune_yield = get_rune_yield_connector(d)

    @staticmethod
    def solve_working_dir_mess():
        cwd = os.getcwd()

        for replacement in ['/tools/debug', '/tests', '/tools']:
            if cwd.endswith(replacement):
                cwd_new = cwd.replace(replacement, '')
                os.chdir(cwd_new)
                cwd_new = os.getcwd()
                print(f'Hey! Auto changed directory. "{cwd}" -> "{cwd_new}"!')
                break

    @property
    def tg_token(self):
        return self.deps.cfg.get('telegram.bot.token')

    async def send_test_tg_message(self, txt, **kwargs):
        return await telegram_send_message_basic(self.tg_token, TG_TEST_USER, txt, **kwargs)

    async def prepare(self, brief=False):
        d = self.deps
        d.make_http_session()

        await d.db.get_redis()

        await self.create_thor_node_connector()

        d.rune_market_fetcher = RuneMarketInfoFetcher(d)

        d.last_block_fetcher.add_subscriber(d.last_block_store)

        brief = brief if self.brief is None else self.brief
        if brief:
            return

        await d.last_block_fetcher.run_once()
        await d.node_info_fetcher.fetch()  # get nodes beforehand
        await d.mimir_const_fetcher.fetch()  # get constants beforehand
        await d.pool_fetcher.fetch()

    async def close(self):
        await self.deps.session.close()

    async def __aenter__(self):
        await self.prepare()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    def __call__(self, brief=False):
        self.brief = brief
        return self


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


class Receiver(INotified):
    # noinspection PyTypeChecker
    async def on_data(self, sender, data):
        if self.callback:
            await self.callback(sender, data)
        else:
            sep()
            if isinstance(data, (list, tuple)):
                for tr in data:
                    if not self.filters or any(text in repr(tr) for text in self.filters):
                        print(f'{self.tag}:  {tr}')
            else:
                print(f'{self.tag}:  {data}')

    def __init__(self, tag='', filters=None, callback=None):
        self.tag = tag
        self.filters = filters
        self.callback = callback


def load_sample_txs(name):
    data = load_json(name)
    parser = MidgardParserV2(network_id=NetworkIdents.MAINNET)
    r = parser.parse_tx_response(data)
    return r.txs


async def demo_run_txs_example_file(fetcher_tx: TxFetcher, filename):
    txs = load_sample_txs(f'tests/sample_data/{filename}')
    txs = fetcher_tx.merge_related_txs(txs)
    await fetcher_tx.pass_data_to_listeners(txs, fetcher_tx)


def save_and_show_pic(pic, show=True, name='pic'):
    if not pic:
        return

    if name.lower().endswith('.png'):
        name = name[:-4]

    filepath = f'../temp/{name}.png'

    with open(filepath, 'wb') as f:
        pic_bio = img_to_bio(pic, os.path.basename(filepath))
        f.write(pic_bio.getbuffer())

    print(f'Pic saved to "{filepath}"')

    if show:
        os.system(f'open "{filepath}"')
