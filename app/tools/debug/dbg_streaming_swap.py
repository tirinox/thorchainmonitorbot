import asyncio

from proto.types import MsgDeposit, MsgObservedTxIn
from services.jobs.fetch.streaming_swaps import StreamingSwapFechter
from services.jobs.fetch.tx import TxFetcher
from services.jobs.scanner.event_db import EventDatabase
from services.jobs.scanner.native_actions import NativeActionExtractor
from services.jobs.scanner.native_scan import NativeScannerBlock
from services.jobs.user_counter import UserCounter
from services.jobs.volume_filler import VolumeFillerUpdater
from services.jobs.volume_recorder import VolumeRecorder
from services.lib.money import DepthCurve, Asset
from services.lib.texts import sep
from services.lib.w3.aggregator import AggregatorDataExtractor
from services.lib.w3.dex_analytics import DexAnalyticsCollector
from services.models.tx import ThorTxType, ThorTx
from services.notify.types.dex_report_notify import DexReportNotifier
from services.notify.types.s_swap_notify import StreamingSwapStartTxNotifier
from services.notify.types.tx_notify import SwapTxNotifier
from tools.lib.lp_common import LpAppFramework


# 1)
# Memo:  =:ETH.THOR:0x8d2e7cab1747f98a7e1fa767c9ef62132e4c31db:139524325459200/9/99:t:30
# Mdg: https://midgard.ninerealms.com/v2/actions?txid=75327336C1EC3FE39D1DECB06C5F05756FAA5C28E0ACC777239F98D7F2903589
# VB: https://viewblock.io/thorchain/tx/75327336C1EC3FE39D1DECB06C5F05756FAA5C28E0ACC777239F98D7F2903589
# Inb: https://thornode.ninerealms.com/thorchain/tx/75327336C1EC3FE39D1DECB06C5F05756FAA5C28E0ACC777239F98D7F2903589
# Block: min = 12079656
# Block outbound : 17879640, finalized 12081263
# Block failed sub swap? 12080322

# 2)
#  030E71AD7F00A9273ADFFF6327069264FBE6296119CFFC9E6A1C174E35F87315
#  ETH => [ss, aff] => ETH.XDEFI
#   "memo": "=:ETH.XDEFI:0xc8Ba8c8E2D86d1Cf614325ceC04151D24Ed72DDa:4261584533288/9/65:t:15"
# Inb: https://thornode.ninerealms.com/thorchain/tx/030E71AD7F00A9273ADFFF6327069264FBE6296119CFFC9E6A1C174E35F87315


# 3)
#  026170F3A6E8EA8A9BA1DDBB106536390C086B64D8E157F31E65789A31841284
# BTC.BTC => BNB (12132219, obs 1)

# 4) rare!!
# https://viewblock.io/thorchain/tx/1E67334A573AC5AA87084836E7CAEC77CC9716A6A39C03A462DC623322E0E3E5
# This is streaming swap of synth!


# 5) Simple ARB: Rune -> synth, no aff, no stream
# 1516681B16786D7F0721942685162510C77A0022F74FF88D9A73C5EC6E5AB46C
# https://midgard.ninerealms.com/v2/actions?txid=1516681B16786D7F0721942685162510C77A0022F74FF88D9A73C5EC6E5AB46C
# https://viewblock.io/thorchain/tx/1516681B16786D7F0721942685162510C77A0022F74FF88D9A73C5EC6E5AB46C
# 12176322

# 6) RUNE => synthAVAX (549AE165C4156F08DEFDC8BC87890A5F630C759308AFC39834AC629518422495)
# With Aff, Streaming
# No Aff swap, because input is Rune!
#

async def debug_fetch_ss(app: LpAppFramework):
    ssf = StreamingSwapFechter(app.deps)
    data = await ssf.run_once()
    print(data)


async def debug_block_analyse(app: LpAppFramework):
    scanner = NativeScannerBlock(app.deps)
    # await scanner.run()
    blk = await scanner.fetch_one_block(12209517)
    sep()

    naex = NativeActionExtractor(app.deps)
    actions = await naex.on_data(None, blk)
    print(actions)


async def debug_full_pipeline(app, start=None, tx_id=None, single_block=False):
    d = app.deps

    # Block scanner: the source of the river
    d.block_scanner = NativeScannerBlock(d, last_block=start)
    d.block_scanner.one_block_per_run = single_block
    d.block_scanner.allow_jumps = False

    # Just to check stability
    user_counter = UserCounter(d)
    d.block_scanner.add_subscriber(user_counter)

    # Extract ThorTx from BlockResult
    native_action_extractor = NativeActionExtractor(d)
    native_action_extractor.dbg_open_file(f'../temp/{tx_id}.txt')
    if tx_id:
        native_action_extractor.dbg_watch_swap_id = tx_id
        native_action_extractor._db.dbg_only_tx_id = tx_id

    await native_action_extractor._db.backup('../temp/ev_db_backup_everything.json')
    d.block_scanner.add_subscriber(native_action_extractor)

    # Enrich with aggregator data
    aggregator = AggregatorDataExtractor(d)
    native_action_extractor.add_subscriber(aggregator)

    # Volume filler (important)
    volume_filler = VolumeFillerUpdater(d)
    aggregator.add_subscriber(volume_filler)

    # Just to check stability
    d.dex_analytics = DexAnalyticsCollector(d)
    aggregator.add_subscriber(d.dex_analytics)

    # Just to check stability
    d.volume_recorder = VolumeRecorder(d)
    volume_filler.add_subscriber(d.volume_recorder)

    # # Just to check stability: DEX reports
    dex_report_notifier = DexReportNotifier(d, d.dex_analytics)
    volume_filler.add_subscriber(dex_report_notifier)
    dex_report_notifier.add_subscriber(d.alert_presenter)

    # Swap notifier (when it finishes)
    curve_pts = d.cfg.get_pure('tx.curve', default=DepthCurve.DEFAULT_TX_VS_DEPTH_CURVE)
    curve = DepthCurve(curve_pts)

    swap_notifier_tx = SwapTxNotifier(d, d.cfg.tx.swap, curve=curve)
    swap_notifier_tx.dbg_evaluate_curve_for_pools()
    volume_filler.add_subscriber(swap_notifier_tx)
    swap_notifier_tx.add_subscriber(d.alert_presenter)

    # When SS starts we do notify as well
    stream_swap_notifier = StreamingSwapStartTxNotifier(d)
    d.block_scanner.add_subscriber(stream_swap_notifier)
    stream_swap_notifier.add_subscriber(d.alert_presenter)
    # await stream_swap_notifier.clear_seen_cache()

    # Run all together
    if single_block:
        await d.block_scanner.run_once()
    else:
        while True:
            await d.block_scanner.run()
            await asyncio.sleep(5.9)


async def debug_detect_start_on_deposit_rune(app):
    scanner = NativeScannerBlock(app.deps)
    blk = await scanner.fetch_one_block(12079656)  # RUNE => ETH.THOR
    sss = StreamingSwapStartTxNotifier(app.deps)
    deposits = blk.find_tx_by_type(MsgDeposit)

    results = sss.detector.handle_deposits(deposits)
    print(results)


async def demo_search_for_deposit_streaming_synth(app):
    tx_fetcher = TxFetcher(app.deps, tx_types=(ThorTxType.TYPE_SWAP,))
    txs = await tx_fetcher.fetch_one_batch(tx_types=tx_fetcher.tx_types)
    next_token = txs.next_page_token

    for page in range(1000):
        txs = await tx_fetcher.fetch_one_batch(next_page_token=next_token)
        next_token = txs.next_page_token

        for tx in txs.txs:
            if not tx.meta_swap:
                continue
            tx: ThorTx
            if Asset(tx.first_input_tx.first_asset).is_synth:
                if tx.meta_swap.parsed_memo.is_streaming:
                    sep('BINGO')
                    print(tx)


async def debug_tx_records(app: LpAppFramework, tx_id):
    ev_db = EventDatabase(app.deps.db)

    props = await ev_db.read_tx_status(tx_id)
    sep('swap')
    print(props)

    sep('tx')
    tx = props.build_tx()
    print(tx)


async def debug_detect_start_on_external_tx(app: LpAppFramework):
    scanner = NativeScannerBlock(app.deps)
    sss = StreamingSwapStartTxNotifier(app.deps)

    # 12132229 vs 12136527

    sep('BLOCK 12132229')

    blk = await scanner.fetch_one_block(12132223)
    deposits = list(blk.find_tx_by_type(MsgObservedTxIn))
    results = sss.detector.handle_observed_txs(deposits)
    print(results)

    sep()


async def run():
    app = LpAppFramework()
    async with app(brief=True):
        await app.deps.pool_fetcher.reload_global_pools()
        await app.deps.last_block_fetcher.run_once()

        # await debug_fetch_ss(app)
        # await debug_block_analyse(app)
        # await debug_full_pipeline(app, start=12132219)
        # await debug_tx_records(app, 'DB3185B2BC24208634473696D0A01D27A43A91AFFB74F2A3209A5285326D2026')
        #
        await debug_full_pipeline(
            app,
            start=12209500,
            # tx_id='x',
            # single_block=True
        )

        # todo: check Tg (refunds, bugs?)

        # await debug_detect_start_on_deposit_rune(app)
        # await debug_detect_start_on_external_tx(app)


if __name__ == '__main__':
    asyncio.run(run())
