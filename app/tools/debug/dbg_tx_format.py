import asyncio
import random
from typing import List

from localization.languages import Language
from localization.manager import BaseLocalization
from services.jobs.affiliate_merge import AffiliateTXMerger, ZERO_HASH
from services.jobs.fetch.tx import TxFetcher
from services.jobs.volume_filler import VolumeFillerUpdater
from services.lib.constants import Chains, thor_to_float
from services.lib.delegates import INotified
from services.lib.explorers import get_explorer_url_to_address, get_explorer_url_to_tx
from services.lib.midgard.name_service import NameMap
from services.lib.midgard.parser import get_parser_by_network_id
from services.lib.midgard.urlgen import free_url_gen
from services.lib.money import DepthCurve
from services.lib.texts import sep
from services.lib.w3.aggregator import AggregatorDataExtractor
from services.models.pool_info import PoolInfo
from services.models.tx import ThorTxType, ThorTx
from services.notify.alert_presenter import AlertPresenter
from services.notify.types.tx_notify import SwitchTxNotifier, SwapTxNotifier, LiquidityTxNotifier
from tools.lib.lp_common import LpAppFramework, load_sample_txs, Receiver


async def midgard_test_kill_switch(app, mdg):
    switch_helper = SwitchTxNotifier(app.deps, app.deps.cfg.tx.switch, tx_types=(ThorTxType.TYPE_SWITCH,),
                                     curve=DepthCurve.default())

    q_path = free_url_gen.url_for_tx(0, 50,
                                     types='switch',
                                     txid='24CD2813F16DEB7342509840DA08C7FD962C6D5F830EFCF31438C941D5F22775')
    ex_tx = await load_tx(app, mdg, q_path)
    ex_tx.rune_amount = switch_helper.calculate_killed_rune(ex_tx.asset_amount, ex_tx.height_int)

    class Fake(INotified):
        async def on_data(self, sender, data):
            print(data)

    alert_presenter = AlertPresenter(app.deps.broadcaster, app.deps.name_service)

    switch_helper.add_subscriber(Fake())
    switch_helper.add_subscriber(alert_presenter)

    await switch_helper.on_data(switch_helper, [ex_tx])
    sep()

    # for loc_name in (Language.RUSSIAN, Language.ENGLISH, Language.ENGLISH_TWITTER):
    #     loc = app.deps.loc_man.get_from_lang(loc_name)
    #     print(loc.__class__.__name__)
    #     await send_tx_notification(app, ex_tx, loc)

    await asyncio.sleep(10.0)


async def midgard_test_1(app):
    q_path = free_url_gen.url_for_tx(0, 50,
                                     tx_type=ThorTxType.TYPE_ADD_LIQUIDITY,
                                     txid='58B3D28E121A34BCE2D31018C00C660942088BC548171A427A51F6825ED77142')
    await present_one_aff_tx(app, q_path)
    q_path = free_url_gen.url_for_tx(0, 50,
                                     tx_type=ThorTxType.TYPE_SWAP,
                                     txid='7F98B4867018DC97C1DC8A6C34E1E597641FC306093B70AB41F156C85D0CD01E')
    await present_one_aff_tx(app, q_path)
    q_path = free_url_gen.url_for_tx(0, 50, address='bnb10gh0p6thzjz54jqy9lg0rv733fnl0vqmc789pp')
    await present_one_aff_tx(app, q_path, find_aff=True)


async def demo_midgard_test_large_ilp(app):
    q_path = free_url_gen.url_for_tx(0, 50,
                                     tx_type=ThorTxType.TYPE_WITHDRAW,
                                     txid='C3BC98CB15022DBA8C5BAEC3C3637FD0BBD55CB7F7000BB62594C234C219E798')
    await present_one_aff_tx(app, q_path)


async def demo_savers_add(app):
    q_path = free_url_gen.url_for_tx(0, 50,
                                     tx_type=ThorTxType.TYPE_ADD_LIQUIDITY,
                                     txid='B380846D04AFB83961D2728177B10D593E1C144A534A21A443366D233971A135')
    # txid='413768826A02E8EA4068A2F35A7941008A15A18F7E76E49B8602BD99D840B721')
    await present_one_aff_tx(app, q_path)


async def demo_test_savers_vaults(app):
    q_path = free_url_gen.url_for_tx(0, 50, txid='050000225130CE9C5DBDDF0D1821036FC1CB7473A01EA41BB4F1EB5E3431A036')
    await present_one_aff_tx(app, q_path, find_aff=False)


async def demo_test_aff_add_liq(app):
    q_path = free_url_gen.url_for_tx(0, 50,
                                     tx_type=ThorTxType.TYPE_ADD_LIQUIDITY,
                                     txid='CBC44B4E2A6332692BD1A3CCE7817F0CBE8AB2CFDC10470327B3057FA1CD8017')
    await present_one_aff_tx(app, q_path)


async def demo_aggr_aff(app):
    # A3C95CE6146AA7A4651F34E12E1DAAB65AF399563CA7CBB3DC51EF5B623B0270
    q_path = free_url_gen.url_for_tx(0, 50, txid='DD68C004C448E0813BDB8BACED6F6A3D62298FDB74D6882D9887662DCF284EA3')
    await present_one_aff_tx(app, q_path)


async def demo_aggr_aff_2(app):
    """
    Midgard URL: https://midgard.ninerealms.com/v2/actions?txid=E6885BE2566B5D6BF49532CE97E65F1BBA3C9EDCA1BD95B9D34F3619AA41F656
    Viewblock URL: https://viewblock.io/thorchain/tx/E6885BE2566B5D6BF49532CE97E65F1BBA3C9EDCA1BD95B9D34F3619AA41F656
    """
    q_path = free_url_gen.url_for_tx(0, 50, txid='E6885BE2566B5D6BF49532CE97E65F1BBA3C9EDCA1BD95B9D34F3619AA41F656')
    await present_one_aff_tx(app, q_path)


async def demo_test_2(app):
    q_path = free_url_gen.url_for_tx(0, 50, txid='7D72CBE466F8E817B700D11D0EDB8FE6183B8DD13912F0810FFD87BE708363E9')
    await present_one_aff_tx(app, q_path)


async def demo_same_merge_swap(app):
    # 4931F82A96196AD5393BB27A32F9EF98B7D80E46035EC6700E4BADF1B75129AC
    q_path = free_url_gen.url_for_tx(0, 50, txid='4931F82A96196AD5393BB27A32F9EF98B7D80E46035EC6700E4BADF1B75129AC')
    await present_one_aff_tx(app, q_path)


async def demo_withdraw_savers(app):
    q_path = free_url_gen.url_for_tx(0, 50,
                                     txid='C24DF9D0A379519EBEEF2DBD50F5AD85AB7A5B75A2F3C571E185202EE2E9876F',
                                     # txid='59A5981184350A481F02FC9D8782FF114A4A010E0FE9C26630089D0944DC42AF',
                                     tx_type=ThorTxType.TYPE_WITHDRAW)
    await present_one_aff_tx(app, q_path)


async def demo_add_savers(app):
    q_path = free_url_gen.url_for_tx(0, 50,
                                     txid='2A36FD67A32D47C9B7B1821197A8EF9F3C688CAB8979C43F235B8664563009CF',
                                     tx_type=ThorTxType.TYPE_ADD_LIQUIDITY)
    await present_one_aff_tx(app, q_path)


async def midgard_test_donate(app, mdg, tx_parser):
    q_path = free_url_gen.url_for_tx(0, 10, types='donate')
    j = await mdg.request(q_path)
    txs = tx_parser.parse_tx_response(j).txs
    await send_tx_notification(app, random.sample(txs, 1)[0])


async def present_one_aff_tx(app, q_path, find_aff=False):
    mdg = app.deps.midgard_connector
    ex_tx = await load_tx(app, mdg, q_path, find_aff)
    await send_tx_notification(app, ex_tx)


async def demo_find_last_savers_additions(app: LpAppFramework):
    d = app.deps
    fetcher_tx = TxFetcher(d, tx_types=(ThorTxType.TYPE_ADD_LIQUIDITY,))

    aggregator = AggregatorDataExtractor(d)
    fetcher_tx.add_subscriber(aggregator)

    volume_filler = VolumeFillerUpdater(d)
    aggregator.add_subscriber(volume_filler)

    txs = await fetcher_tx.fetch_all_tx(liquidity_change_only=True, max_pages=5)
    for tx in txs:
        if tx.first_pool == 'BTC/BTC':
            url = get_explorer_url_to_address(d.cfg.network_id, Chains.THOR, tx.sender_address)
            amt = thor_to_float(tx.first_input_tx.first_amount)
            print(f'{tx.first_pool} ({url}) amount = {amt} {tx.first_input_tx.first_asset}')
            sep()


async def load_tx(app, mdg, q_path, find_aff=False):
    tx_parser = get_parser_by_network_id(app.deps.cfg.network_id)
    j = await mdg.request(q_path)
    txs = tx_parser.parse_tx_response(j).txs
    txs_merged = AffiliateTXMerger().merge_affiliate_txs(txs)
    tx = next(tx for tx in txs_merged if tx.affiliate_fee > 0) if find_aff else txs_merged[0]
    return tx


async def send_tx_notification(app, ex_tx, loc: BaseLocalization = None):
    await app.deps.pool_fetcher.run_once()
    pool = ex_tx.first_pool_l1
    pool_info: PoolInfo = app.deps.price_holder.pool_info_map.get(pool)
    full_rune = ex_tx.calc_full_rune_amount(app.deps.price_holder.pool_info_map)
    print(f'{ex_tx.affiliate_fee = }')
    rune_price = app.deps.price_holder.usd_per_rune
    print(f'{ex_tx.get_affiliate_fee_usd(rune_price) = } $')
    print(f'{full_rune = } R')

    nm = NameMap({}, {})

    for lang in [Language.RUSSIAN, Language.ENGLISH, Language.ENGLISH_TWITTER]:
        loc = app.deps.loc_man[lang]
        text = loc.notification_text_large_single_tx(ex_tx, rune_price, pool_info,
                                                     name_map=nm,
                                                     mimir=app.deps.mimir_const_holder)
        await app.send_test_tg_message(text)
        sep()
        print(text)


async def refund_full_rune(app):
    txs = load_sample_txs('./tests/sample_data/refunds.json')
    volume_filler = VolumeFillerUpdater(app.deps)
    await volume_filler.fill_volumes(txs)


async def demo_full_tx_pipeline(app: LpAppFramework, announce=True):
    d = app.deps

    await d.mimir_const_fetcher.run_once()

    fetcher_tx = TxFetcher(d, tx_types=(ThorTxType.TYPE_ADD_LIQUIDITY, ThorTxType.TYPE_WITHDRAW, ThorTxType.TYPE_SWAP))

    aggregator = AggregatorDataExtractor(d)
    fetcher_tx.add_subscriber(aggregator)

    volume_filler = VolumeFillerUpdater(d)
    aggregator.add_subscriber(volume_filler)

    all_accepted_tx_hashes = set()

    async def print_hashes(_, txs: List[ThorTx]):
        hashes = {tx.tx_hash for tx in txs}
        sep()
        print('Accepted hashes = ', hashes)
        print(f'Pending hashes = ({len(fetcher_tx.pending_hash_to_height)}) {fetcher_tx.pending_hash_to_height}')

        if hashes & all_accepted_tx_hashes:
            sep()
            print('Attention! Duplicates found!')
            print('Duplicates found: ', hashes & all_accepted_tx_hashes)
            sep()
        all_accepted_tx_hashes.update(hashes)

    aggregator.add_subscriber(Receiver(callback=print_hashes))

    if announce:
        curve = DepthCurve.default()
        swap_notifier_tx = SwapTxNotifier(d, d.cfg.tx.swap, curve=curve)
        swap_notifier_tx.curve_mult = 0.00001
        swap_notifier_tx.min_usd_total = 5000.0
        swap_notifier_tx.aff_fee_min_usd = 0.3
        volume_filler.add_subscriber(swap_notifier_tx)
        swap_notifier_tx.add_subscriber(app.deps.alert_presenter)

        liq_notifier_tx = LiquidityTxNotifier(d, d.cfg.tx.liquidity, curve=curve)
        liq_notifier_tx.curve_mult = 0.1
        liq_notifier_tx.min_usd_total = 50.0
        liq_notifier_tx.ilp_paid_min_usd = 10.0
        volume_filler.add_subscriber(liq_notifier_tx)
        liq_notifier_tx.add_subscriber(app.deps.alert_presenter)

        # swap_notifier_tx.add_subscriber(Receiver('Swap TX'))
        # liq_notifier_tx.add_subscriber(Receiver('Liq TX'))

    # run the pipeline!
    await fetcher_tx.run()

    # await demo_run_txs_example_file(fetcher_tx, 'swap_with_aff_new.json')
    # await demo_run_txs_example_file(fetcher_tx, 'withdraw_ilp.json')
    # await demo_run_txs_example_file(fetcher_tx, 'swap_synth_synth.json')
    # await demo_run_txs_example_file(fetcher_tx, 'add_withdraw_big.json')
    await asyncio.sleep(10.0)


async def demo_verify_tx_scanner_in_the_past(app: LpAppFramework):
    d = app.deps

    fetcher_tx = TxFetcher(d)

    aggregator = AggregatorDataExtractor(d)
    fetcher_tx.add_subscriber(aggregator)

    volume_filler = VolumeFillerUpdater(d)
    aggregator.add_subscriber(volume_filler)

    page = 0

    n_zeros = 0

    while True:
        batch_txs = await fetcher_tx.fetch_one_batch(page, tx_types=ThorTxType.ALL_EXCEPT_DONATE)
        batch_txs = batch_txs.txs
        batch_txs = fetcher_tx.merge_related_txs(batch_txs)
        for tx in batch_txs:
            if tx.tx_hash == ZERO_HASH:
                n_zeros += 1
                continue

        print(f'TX hash => {n_zeros} zeros')

        await volume_filler.on_data(fetcher_tx, batch_txs)

        page += 1


async def find_affiliate_txs(app: LpAppFramework, desired_count=5, tx_types=None):
    d = app.deps
    fetcher_tx = TxFetcher(d)

    interesting_txs = []
    page = 0
    tx_types = tx_types or (ThorTxType.TYPE_ADD_LIQUIDITY, ThorTxType.TYPE_WITHDRAW, ThorTxType.TYPE_SWAP)
    while len(interesting_txs) < desired_count:
        page_results = await fetcher_tx.fetch_one_batch(page, tx_types=tx_types)
        for tx in page_results.txs:
            if tx.meta_swap and tx.meta_swap.affiliate_address:
                interesting_txs.append(tx)
                print(f'Found interesting tx: {tx}')
        page += 1



async def demo_find_missed_txs_swap(app: LpAppFramework):
    d = app.deps
    fetcher_tx = TxFetcher(d, tx_types=(ThorTxType.TYPE_SWAP,))

    aggregator = AggregatorDataExtractor(d)
    fetcher_tx.add_subscriber(aggregator)

    volume_filler = VolumeFillerUpdater(d)
    aggregator.add_subscriber(volume_filler)

    page = 50
    while True:
        txs = await fetcher_tx.fetch_one_batch(page, tx_types=(ThorTxType.TYPE_SWAP,))
        for tx in txs.txs:
            if 'ETH.ETH' in tx.pools and tx.rune_amount > 100_000:
                url = get_explorer_url_to_tx(d.cfg.network_id, Chains.THOR, tx.tx_hash)
                amt = thor_to_float(tx.first_input_tx.first_amount)
                print(f'{tx.first_pool} ({url}) amount = {amt} {tx.first_input_tx.first_asset}')
                sep()
        page += 1


async def main():
    app = LpAppFramework()
    await app.prepare(brief=True)

    # await midgard_test_donate(app, mdg, tx_parser)
    # await midgard_test_1(app, mdg, tx_parser)
    # await midgard_test_kill_switch(app)
    # await refund_full_rune(app)
    # await demo_midgard_test_large_ilp(app)
    await demo_full_tx_pipeline(app, announce=True)
    # await demo_test_savers_vaults(app)
    # await demo_aggr_aff_2(app)
    # await demo_test_aff_add_liq(app)
    # await demo_test_2(app)
    # await demo_aggr_aff(app)
    # await demo_same_merge_swap(app)
    # await demo_withdraw_savers(app)
    # await demo_add_savers(app)
    # await demo_find_last_savers_additions(app)
    # await demo_midgard_test_large_ilp(app)
    # await demo_savers_add(app)
    # await demo_verify_tx_scanner_in_the_past(app)
    # await find_affiliate_txs(app, 1, (ThorTxType.TYPE_SWAP,))
    # await demo_find_aggregator_error(app)
    # await demo_find_missed_txs_swap(app)


if __name__ == '__main__':
    asyncio.run(main())
