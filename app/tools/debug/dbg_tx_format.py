import asyncio
import random

from localization.languages import Language
from localization.manager import BaseLocalization
from services.jobs.affiliate_merge import AffiliateTXMerger
from services.jobs.fetch.tx import TxFetcher
from services.jobs.volume_filler import VolumeFillerUpdater
from services.lib.delegates import INotified
from services.lib.midgard.name_service import NameMap
from services.lib.midgard.parser import get_parser_by_network_id
from services.lib.midgard.urlgen import free_url_gen
from services.lib.money import DepthCurve, Asset
from services.lib.texts import sep
from services.lib.w3.aggregator import AggregatorDataExtractor
from services.models.pool_info import PoolInfo
from services.models.tx import ThorTxType
from services.notify.alert_presenter import AlertPresenter
from services.notify.types.tx_notify import SwitchTxNotifier, SwapTxNotifier, LiquidityTxNotifier
from tools.lib.lp_common import LpAppFramework, load_sample_txs, Receiver, demo_run_txs_example_file


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

    switch_helper.add_subscriber(Fake())
    switch_helper.add_subscriber(alert_presenter)

    await switch_helper.on_data(switch_helper, [ex_tx])
    sep()

    # for loc_name in (Language.RUSSIAN, Language.ENGLISH, Language.ENGLISH_TWITTER):
    #     loc = lp_app.deps.loc_man.get_from_lang(loc_name)
    #     print(loc.__class__.__name__)
    #     await send_tx_notification(lp_app, ex_tx, loc)

    await asyncio.sleep(10.0)


async def midgard_test_1(lp_app):
    q_path = free_url_gen.url_for_tx(0, 50,
                                     tx_type=ThorTxType.TYPE_ADD_LIQUIDITY,
                                     txid='58B3D28E121A34BCE2D31018C00C660942088BC548171A427A51F6825ED77142')
    await present_one_aff_tx(lp_app, q_path)
    q_path = free_url_gen.url_for_tx(0, 50,
                                     tx_type=ThorTxType.TYPE_SWAP,
                                     txid='7F98B4867018DC97C1DC8A6C34E1E597641FC306093B70AB41F156C85D0CD01E')
    await present_one_aff_tx(lp_app, q_path)
    q_path = free_url_gen.url_for_tx(0, 50,
                                     address='bnb10gh0p6thzjz54jqy9lg0rv733fnl0vqmc789pp')
    await present_one_aff_tx(lp_app, q_path, find_aff=True)


async def demo_midgard_test_large_ilp(app):
    q_path = free_url_gen.url_for_tx(0, 50,
                                     tx_type=ThorTxType.TYPE_WITHDRAW,
                                     txid='C3BC98CB15022DBA8C5BAEC3C3637FD0BBD55CB7F7000BB62594C234C219E798')
    await present_one_aff_tx(app, q_path)


async def demo_test_savers_vaults(app):
    q_path = free_url_gen.url_for_tx(0, 50,
                                     tx_type=ThorTxType.TYPE_ADD_LIQUIDITY,
                                     txid='44716F01BF45214AA0A68B98110659ED2D45C98E348CFAC4EB16C1683ADF8F3D')
    await present_one_aff_tx(app, q_path, find_aff=True)


async def demo_aggr_aff(app):
    q_path = free_url_gen.url_for_tx(0, 50,
                                     txid='A3C95CE6146AA7A4651F34E12E1DAAB65AF399563CA7CBB3DC51EF5B623B0270')
    await present_one_aff_tx(app, q_path)


async def midgard_test_donate(lp_app, mdg, tx_parser):
    q_path = free_url_gen.url_for_tx(0, 10, types='donate')
    j = await mdg.request_random_midgard(q_path)
    txs = tx_parser.parse_tx_response(j).txs
    await send_tx_notification(lp_app, random.sample(txs, 1)[0])


async def present_one_aff_tx(lp_app, q_path, find_aff=False):
    mdg = lp_app.deps.midgard_connector
    ex_tx = await load_tx(lp_app, mdg, q_path, find_aff)
    await send_tx_notification(lp_app, ex_tx)


async def load_tx(lp_app, mdg, q_path, find_aff=False):
    tx_parser = get_parser_by_network_id(lp_app.deps.cfg.network_id)
    j = await mdg.request_random_midgard(q_path)
    txs = tx_parser.parse_tx_response(j).txs
    txs_merged = AffiliateTXMerger().merge_affiliate_txs(txs)
    tx = next(tx for tx in txs_merged if tx.affiliate_fee > 0) if find_aff else txs_merged[0]
    return tx


async def send_tx_notification(lp_app, ex_tx, loc: BaseLocalization = None):
    await lp_app.deps.price_pool_fetcher.run_once()
    pool = Asset.from_string(ex_tx.first_pool).native_pool_name
    pool_info: PoolInfo = lp_app.deps.price_holder.pool_info_map.get(pool)
    full_rune = ex_tx.calc_full_rune_amount(lp_app.deps.price_holder.pool_info_map)
    print(f'{ex_tx.affiliate_fee = }')
    rune_price = lp_app.deps.price_holder.usd_per_rune
    print(f'{ex_tx.get_affiliate_fee_usd(rune_price) = } $')
    print(f'{full_rune = } R')
    loc = loc or lp_app.deps.loc_man.default
    nm = NameMap({}, {})
    await lp_app.send_test_tg_message(loc.notification_text_large_single_tx(ex_tx, rune_price, pool_info,
                                                                            name_map=nm))
    sep()
    tw_loc: BaseLocalization = lp_app.deps.loc_man[Language.ENGLISH_TWITTER]
    print(tw_loc.notification_text_large_single_tx(ex_tx, rune_price, pool_info, name_map=nm))


async def refund_full_rune(app):
    txs = load_sample_txs('./tests/sample_data/refunds.json')
    volume_filler = VolumeFillerUpdater(app.deps)
    await volume_filler.fill_volumes(txs)


async def demo_full_tx_pipeline(app: LpAppFramework):
    d = app.deps

    fetcher_tx = TxFetcher(d, tx_types=(ThorTxType.TYPE_ADD_LIQUIDITY,))

    aggregator = AggregatorDataExtractor(d)
    fetcher_tx.add_subscriber(aggregator)

    volume_filler = VolumeFillerUpdater(d)
    aggregator.add_subscriber(volume_filler)

    curve = DepthCurve.default()
    swap_notifier_tx = SwapTxNotifier(d, d.cfg.tx.swap, curve=curve)
    swap_notifier_tx.curve_mult = 0.00001
    swap_notifier_tx.min_usd_total = 0.0
    swap_notifier_tx.aff_fee_min_usd = 0.3
    volume_filler.add_subscriber(swap_notifier_tx)

    liq_notifier_tx = LiquidityTxNotifier(d, d.cfg.tx.liquidity, curve=curve)
    liq_notifier_tx.curve_mult = 0.1
    liq_notifier_tx.ilp_paid_min_usd = 10.0
    volume_filler.add_subscriber(liq_notifier_tx)

    swap_notifier_tx.add_subscriber(Receiver('Swap TX'))
    liq_notifier_tx.add_subscriber(Receiver('Liq TX'))

    swap_notifier_tx.add_subscriber(app.deps.alert_presenter)
    liq_notifier_tx.add_subscriber(app.deps.alert_presenter)

    # run the pipeline!
    await fetcher_tx.run()

    # await demo_run_txs_example_file(fetcher_tx, 'swap_with_aff_new.json')
    # await demo_run_txs_example_file(fetcher_tx, 'withdraw_ilp.json')
    # await demo_run_txs_example_file(fetcher_tx, 'swap_synth_synth.json')
    await demo_run_txs_example_file(fetcher_tx, 'add_withdraw_big.json')
    await asyncio.sleep(10.0)


async def main():
    lp_app = LpAppFramework()
    await lp_app.prepare(brief=True)

    # await midgard_test_donate(lp_app, mdg, tx_parser)
    # await midgard_test_1(lp_app, mdg, tx_parser)
    # await midgard_test_kill_switch(lp_app)
    # await refund_full_rune(lp_app)
    # await demo_midgard_test_large_ilp(lp_app)
    # await demo_full_tx_pipeline(lp_app)
    # await demo_test_savers_vaults(lp_app)
    await demo_aggr_aff(lp_app)


if __name__ == '__main__':
    asyncio.run(main())
