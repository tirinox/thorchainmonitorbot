import asyncio
import random

from localization.manager import BaseLocalization
from services.jobs.affiliate_merge import AffiliateTXMerger
from services.jobs.fetch.tx import TxFetcher
from services.jobs.volume_filler import VolumeFillerUpdater
from services.lib.delegates import INotified
from services.lib.midgard.parser import get_parser_by_network_id
from services.lib.midgard.urlgen import free_url_gen
from services.lib.money import DepthCurve
from services.lib.texts import sep
from services.lib.w3.aggregator import AggregatorDataExtractor
from services.models.pool_info import PoolInfo
from services.models.tx import ThorTxExtended, ThorTxType
from services.notify.alert_presenter import AlertPresenter
from services.notify.types.tx_notify import SwitchTxNotifier, GenericTxNotifier
from tools.debug.dbg_w3 import FilterTxMiddleware
from tools.lib.lp_common import LpAppFramework, load_sample_txs, Receiver


async def main():
    lp_app = LpAppFramework()
    await lp_app.prepare(brief=True)

    # await midgard_test_donate(lp_app, mdg, tx_parser)
    # await midgard_test_1(lp_app, mdg, tx_parser)
    # await midgard_test_kill_switch(lp_app, mdg)
    # await refund_full_rune(lp_app)
    await demo_full_tx_pipeline(lp_app)


async def midgard_test_kill_switch(lp_app, mdg):
    switch_helper = SwitchTxNotifier(lp_app.deps, lp_app.deps.cfg.tx.switch, tx_types=(ThorTxType.TYPE_SWITCH,),
                                     curve=DepthCurve.default())

    q_path = free_url_gen.url_for_tx(0, 50,
                                     types='switch',
                                     txid='24CD2813F16DEB7342509840DA08C7FD962C6D5F830EFCF31438C941D5F22775')
    ex_tx = await load_tx(lp_app, mdg, q_path)
    ex_tx.rune_amount = switch_helper.calculate_killed_rune(ex_tx.asset_amount, ex_tx.height_int)

    class Fake(INotified):
        async def on_data(self, sender, data):
            print(data)

    alert_presenter = AlertPresenter(lp_app.deps.broadcaster, lp_app.deps.name_service)

    switch_helper.subscribe(Fake())
    switch_helper.subscribe(alert_presenter)

    await switch_helper.on_data(switch_helper, [ex_tx])
    sep()

    # for loc_name in (Language.RUSSIAN, Language.ENGLISH, Language.ENGLISH_TWITTER):
    #     loc = lp_app.deps.loc_man.get_from_lang(loc_name)
    #     print(loc.__class__.__name__)
    #     await send_tx_notification(lp_app, ex_tx, loc)

    await asyncio.sleep(10.0)


async def midgard_test_1(lp_app, mdg):
    q_path = free_url_gen.url_for_tx(0, 50,
                                     types='addLiquidity',
                                     txid='58B3D28E121A34BCE2D31018C00C660942088BC548171A427A51F6825ED77142')
    await present_one_aff_tx(lp_app, mdg, q_path)
    q_path = free_url_gen.url_for_tx(0, 50,
                                     types='swap',
                                     txid='7F98B4867018DC97C1DC8A6C34E1E597641FC306093B70AB41F156C85D0CD01E')
    await present_one_aff_tx(lp_app, mdg, q_path)
    q_path = free_url_gen.url_for_tx(0, 50,
                                     address='bnb10gh0p6thzjz54jqy9lg0rv733fnl0vqmc789pp')
    await present_one_aff_tx(lp_app, mdg, q_path, find_aff=True)


async def midgard_test_donate(lp_app, mdg, tx_parser):
    q_path = free_url_gen.url_for_tx(0, 10, types='donate')
    j = await mdg.request_random_midgard(q_path)
    txs = tx_parser.parse_tx_response(j).txs
    await send_tx_notification(lp_app, random.sample(txs, 1)[0])


async def present_one_aff_tx(lp_app, mdg, q_path, find_aff=False):
    ex_tx = await load_tx(lp_app, mdg, q_path, find_aff)
    await send_tx_notification(lp_app, ex_tx)


async def load_tx(lp_app, mdg, q_path, find_aff=False):
    tx_parser = get_parser_by_network_id(lp_app.deps.cfg.network_id)
    j = await mdg.request_random_midgard(q_path)
    txs = tx_parser.parse_tx_response(j).txs
    txs_merged = AffiliateTXMerger().merge_affiliate_txs(txs)
    tx = next(tx for tx in txs_merged if tx.affiliate_fee > 0) if find_aff else txs_merged[0]
    ex_tx = ThorTxExtended.load_from_thor_tx(tx)
    return ex_tx


async def send_tx_notification(lp_app, ex_tx, loc: BaseLocalization = None):
    pool_info: PoolInfo = lp_app.deps.price_holder.pool_info_map.get(ex_tx.first_pool)
    asset_per_rune = pool_info.asset_per_rune if pool_info else 0.0
    full_rune = ex_tx.calc_full_rune_amount(asset_per_rune)
    print(f'{ex_tx.affiliate_fee = }')
    rune_price = lp_app.deps.price_holder.usd_per_rune
    print(f'{ex_tx.get_affiliate_fee_usd(rune_price) = } $')
    print(f'{full_rune = } R')
    loc = loc or lp_app.deps.loc_man.default
    await lp_app.send_test_tg_message(loc.notification_text_large_single_tx(ex_tx, rune_price, pool_info))
    sep()


async def refund_full_rune(app):
    txs = load_sample_txs('./tests/sample_data/refunds.json')
    volume_filler = VolumeFillerUpdater(app.deps)
    await volume_filler.fill_volumes(txs)


async def demo_full_tx_pipeline(app: LpAppFramework):
    d = app.deps

    fetcher_tx = TxFetcher(d)

    aggregator = AggregatorDataExtractor(d)
    fetcher_tx.subscribe(aggregator)

    volume_filler = VolumeFillerUpdater(d)
    aggregator.subscribe(volume_filler)

    curve = DepthCurve.default()
    swap_notifier_tx = GenericTxNotifier(d, d.cfg.tx.swap, tx_types=(ThorTxType.TYPE_SWAP,), curve=curve)
    swap_notifier_tx.curve_mult = 0.0
    swap_notifier_tx.min_usd_total = 0.0
    volume_filler.subscribe(swap_notifier_tx)

    swap_notifier_tx.subscribe(Receiver('TX'))

    # run the pipeline!
    await fetcher_tx.run()


if __name__ == '__main__':
    asyncio.run(main())
