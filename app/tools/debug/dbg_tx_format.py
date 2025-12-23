import asyncio
import random
from typing import List

from api.midgard.name_service import NameMap
from api.midgard.parser import get_parser_by_network_id
from api.midgard.urlgen import free_url_gen
from api.w3.aggregator import AggregatorDataExtractor
from comm.localization.languages import Language
from comm.localization.manager import BaseLocalization
from jobs.fetch.tx import TxFetcher
from jobs.volume_filler import VolumeFillerUpdater
from lib.constants import Chains, thor_to_float, ZERO_HASH
from lib.explorers import get_explorer_url_to_tx
from lib.money import DepthCurve
from lib.texts import sep
from models.memo import ActionType
from models.pool_info import PoolInfo
from models.tx import ThorAction, EventLargeTransaction
from notify.dup_stop import TxDeduplicator
from notify.public.tx_notify import SwapTxNotifier, LiquidityTxNotifier, RefundTxNotifier
from tools.lib.lp_common import LpAppFramework, load_sample_txs, Receiver


async def midgard_test_1(app):
    q_path = free_url_gen.url_for_tx(0, 50,
                                     tx_type=ActionType.ADD_LIQUIDITY,
                                     txid='58B3D28E121A34BCE2D31018C00C660942088BC548171A427A51F6825ED77142')
    await present_one_aff_tx(app, q_path)
    q_path = free_url_gen.url_for_tx(0, 50,
                                     tx_type=ActionType.SWAP,
                                     txid='7F98B4867018DC97C1DC8A6C34E1E597641FC306093B70AB41F156C85D0CD01E')
    await present_one_aff_tx(app, q_path)
    q_path = free_url_gen.url_for_tx(0, 50, address='bnb10gh0p6thzjz54jqy9lg0rv733fnl0vqmc789pp')
    await present_one_aff_tx(app, q_path, find_aff=True)


async def demo_midgard_test_large_ilp(app):
    q_path = free_url_gen.url_for_tx(0, 50,
                                     tx_type=ActionType.WITHDRAW,
                                     txid='C3BC98CB15022DBA8C5BAEC3C3637FD0BBD55CB7F7000BB62594C234C219E798')
    await present_one_aff_tx(app, q_path)



async def demo_test_aff_add_liq(app):
    q_path = free_url_gen.url_for_tx(0, 50,
                                     tx_type=ActionType.ADD_LIQUIDITY,
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


async def midgard_test_donate(app, mdg, tx_parser):
    q_path = free_url_gen.url_for_tx(0, 10, types='donate')
    j = await mdg.request(q_path)
    txs = tx_parser.parse_tx_response(j).txs
    await send_tx_notification(app, random.sample(txs, 1)[0])


async def present_one_aff_tx(app, q_path, find_aff=False):
    mdg = app.deps.midgard_connector
    ex_tx = await load_tx(app, mdg, q_path, find_aff)
    await send_tx_notification(app, ex_tx)


async def load_tx(app, mdg, q_path, find_aff=False):
    tx_parser = get_parser_by_network_id(app.deps.cfg.network_id)
    j = await mdg.request(q_path)
    txs = tx_parser.parse_tx_response(j).txs
    txs_merged = txs
    tx = next(tx for tx in txs_merged if tx.affiliate_fee > 0) if find_aff else txs_merged[0]
    return tx


async def send_tx_notification(app, ex_tx, loc: BaseLocalization = None):
    pool = ex_tx.first_pool_l1
    ph = await app.deps.pool_cache.get()
    pool_info: PoolInfo = ph.pool_info_map.get(pool)
    full_rune = ex_tx.calc_full_rune_amount(ph)

    # profit_calc = StreamingSwapVsCexProfitCalculator(app.deps)
    # if ex_tx.is_of_type(ActionType.SWAP):
    #     await profit_calc.get_cex_data_v2(ex_tx)

    print(f'{ex_tx.affiliate_fee = }')
    rune_price = ph.usd_per_rune
    print(f'{ex_tx.get_affiliate_fee_usd(rune_price) = } $')
    print(f'{full_rune = } R')

    nm = NameMap.empty()

    for lang in [Language.RUSSIAN, Language.ENGLISH, Language.ENGLISH_TWITTER]:
        loc = app.deps.loc_man[lang]
        text = loc.notification_text_large_single_tx(
            EventLargeTransaction(
                ex_tx, rune_price, pool_info,
            ), name_map=nm
        )
        await app.send_test_tg_message(text)
        sep()
        print(text)


async def refund_full_rune(app):
    txs = load_sample_txs('./tests/sample_data/refunds.json')
    volume_filler = VolumeFillerUpdater(app.deps)
    await volume_filler.fill_volumes(txs)


def foo_dedup(d):
    return TxDeduplicator(d.db, "_debug:tx_fetcher:last_seen")


async def demo_full_tx_pipeline(app: LpAppFramework, announce=True,
                                tx_types=(ActionType.ADD_LIQUIDITY, ActionType.WITHDRAW, ActionType.SWAP),
                                only_asset=None, clear=True):
    d = app.deps

    fetcher_tx = TxFetcher(d, tx_types=tx_types, only_asset=only_asset)
    fetcher_tx.deduplicator = foo_dedup(d)
    if clear:
        await fetcher_tx.deduplicator.clear()

    aggregator = AggregatorDataExtractor(d)
    fetcher_tx.add_subscriber(aggregator)

    volume_filler = VolumeFillerUpdater(d)
    aggregator.add_subscriber(volume_filler)

    all_accepted_tx_hashes = set()

    async def print_hashes(_, txs: List[ThorAction]):
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
        batch_txs = await fetcher_tx.fetch_one_batch(page, tx_types=ActionType.SWAP)
        batch_txs = batch_txs.txs
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
    tx_types = tx_types or (ActionType.ADD_LIQUIDITY, ActionType.WITHDRAW, ActionType.SWAP)
    while len(interesting_txs) < desired_count:
        page_results = await fetcher_tx.fetch_one_batch(page, tx_types=tx_types)
        for tx in page_results.txs:
            if tx.meta_swap and tx.meta_swap.affiliate_address:
                interesting_txs.append(tx)
                print(f'Found interesting tx: {tx}')
        page += 1


async def demo_find_missed_txs_swap(app: LpAppFramework):
    d = app.deps
    fetcher_tx = TxFetcher(d, tx_types=(ActionType.SWAP,))

    aggregator = AggregatorDataExtractor(d)
    fetcher_tx.add_subscriber(aggregator)

    volume_filler = VolumeFillerUpdater(d)
    aggregator.add_subscriber(volume_filler)

    page = 50
    while True:
        txs = await fetcher_tx.fetch_one_batch(page, tx_types=(ActionType.SWAP,))
        for tx in txs.txs:
            if 'ETH.ETH' in tx.pools and tx.rune_amount > 100_000:
                url = get_explorer_url_to_tx(d.cfg.network_id, Chains.THOR, tx.tx_hash)
                amt = thor_to_float(tx.first_input_tx.first_amount)
                print(f'{tx.first_pool} ({url}) amount = {amt} {tx.first_input_tx.first_asset}')
                sep()
        page += 1


async def demo_swap_synth(app):
    q_path = free_url_gen.url_for_tx(0, 50,
                                     txid='CD95B08C68AD0EC93E13A586F04A7F6BC6EE4B70471F84F1BD3D4933EA86FAA2',
                                     tx_type=ActionType.SWAP)
    await present_one_aff_tx(app, q_path)


async def demo_swap_adjust_liquidity(app):
    d = app.deps

    fetcher = TxFetcher(d, tx_types=(ActionType.SWAP,))
    fetcher.deduplicator = foo_dedup(d)
    await fetcher.deduplicator.clear()

    txid = '9EAF7243561F4FDAA35ABDD74D6872EA1A08F8BF67466D6EA8306ADD2E45A10F'
    txs = await fetcher.fetch_one_batch(0, txid=txid)
    tx = txs.txs[0]
    tx.meta_swap.liquidity_fee = 99999
    tx.full_volume_in_rune = 100000

    curve = DepthCurve.default()

    swap_notifier_tx = SwapTxNotifier(d, d.cfg.tx.swap, curve=curve)

    swap_notifier_tx.curve_mult = 0.00001
    swap_notifier_tx.min_usd_total = 0.1

    swap_notifier_tx.add_subscriber(d.alert_presenter)
    swap_notifier_tx.no_repeat_protection = False
    r = await swap_notifier_tx.on_data(None, [tx])
    print(r)

    await asyncio.sleep(5.0)

    # q_path = free_url_gen.url_for_tx(0, 50,
    #                                  txid='9EAF7243561F4FDAA35ABDD74D6872EA1A08F8BF67466D6EA8306ADD2E45A10F',
    #                                  tx_type=ActionType.SWAP)
    #
    # await present_one_aff_tx(app, q_path)


async def demo_swap_with_refund_and_incorrect_savings_vs_cex(app):
    # txid = '98A0E24728729721BC6295A85991D28BF4A26A8767D773FD6BA53E6742F70631'  # no refund, synth
    # txid = 'E22E41745A9422B12C02E26F12BE79D621DDCB3CA1BC954CCAD2AB4792DE5AC7'  # with refund BTC -> ETH + BTC
    txid = '6604B9BC94BC50158BE5B4486178AE880F01E6532893F357C4ACBA1E83FFCB9F'  # normal SS

    q_path = free_url_gen.url_for_tx(0, 50,
                                     txid=txid,
                                     tx_type=ActionType.SWAP)
    await present_one_aff_tx(app, q_path)


def get_curve(d):
    curve_pts = d.cfg.get_pure('tx.curve', default=DepthCurve.DEFAULT_TX_VS_DEPTH_CURVE)
    curve = DepthCurve(curve_pts)
    return curve


async def dbg_refund_spam(app):
    # block_start = 13813213

    d = app.deps

    q_path = free_url_gen.url_for_tx(0, 20, address='thor1wx5av89rghsmgh2vh40aknx7csvs7xj2cr474n',
                                     tx_type=ActionType.REFUND)

    j = await d.midgard_connector.request(q_path)
    tx_parser = get_parser_by_network_id(app.deps.cfg.network_id)
    txs = tx_parser.parse_tx_response(j).txs

    d.cfg.contents['tx']['refund']['cooldown'] = 3.5

    refund_notifier = RefundTxNotifier(d, d.cfg.tx.refund, curve=get_curve(d))
    refund_notifier.add_subscriber(d.alert_presenter)

    volume_filler = VolumeFillerUpdater(d)
    volume_filler.add_subscriber(refund_notifier)

    for i, tx in enumerate(txs, start=1):
        sep(i)

        await refund_notifier.deduplicator.forget(tx.tx_hash)
        await volume_filler.on_data(None, [tx])
        await asyncio.sleep(1)


async def main():
    app = LpAppFramework()
    

    # await midgard_test_donate(app, mdg, tx_parser)
    # await midgard_test_1(app, mdg, tx_parser)
    # await refund_full_rune(app)
    # await demo_midgard_test_large_ilp(app)
    # await demo_full_tx_pipeline(app, announce=True)
    # await demo_aggr_aff_2(app)
    # await demo_test_aff_add_liq(app)
    # await demo_test_2(app)
    # await demo_aggr_aff(app)
    # await demo_verify_tx_scanner_in_the_past(app)
    # await find_affiliate_txs(app, 1, (ThorTxType.TYPE_SWAP,))
    # await demo_find_aggregator_error(app)
    # await demo_find_missed_txs_swap(app)
    # await demo_swap_adjust_liquidity(app)
    # await demo_swap_synth(app)
    # await demo_swap_with_refund_and_incorrect_savings_vs_cex(app)
    # await dbg_refund_spam(app)


if __name__ == '__main__':
    asyncio.run(main())
