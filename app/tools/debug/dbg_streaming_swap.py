import asyncio
import logging

from api.profit_against_cex import StreamingSwapVsCexProfitCalculator
from api.w3.aggregator import AggregatorDataExtractor
from api.w3.dex_analytics import DexAnalyticsCollector
from jobs.fetch.streaming_swaps import StreamingSwapFechter
from jobs.fetch.tx import TxFetcher
from jobs.scanner.event_db import EventDatabase
from jobs.scanner.native_scan import BlockScanner
from jobs.scanner.scan_cache import BlockScannerCached
from jobs.scanner.swap_extractor import SwapExtractorBlock
from jobs.user_counter import UserCounterMiddleware
from jobs.volume_filler import VolumeFillerUpdater
from lib.money import DepthCurve
from lib.texts import sep
from lib.utils import setup_logs
from models.asset import Asset, AssetRUNE
from models.memo import ActionType
from models.tx import ThorAction
from notify.public.dex_report_notify import DexReportNotifier
from notify.public.s_swap_notify import StreamingSwapStartTxNotifier
from notify.public.tx_notify import SwapTxNotifier
from tools.lib.lp_common import LpAppFramework

BlockScannerClass = BlockScannerCached
print(BlockScannerClass, ' <= look!')
BlockScannerClass = BlockScanner


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


async def debug_block_analyse(app: LpAppFramework, block):
    scanner = BlockScannerClass(app.deps)
    # await scanner.run()
    blk = await scanner.fetch_one_block(block)
    sep()

    naex = SwapExtractorBlock(app.deps)
    actions = await naex.on_data(None, blk)
    print(actions)


async def debug_full_pipeline(app, start=None, tx_id=None, single_block=False):
    d = app.deps

    # Block scanner: the source of the river
    d.block_scanner = BlockScannerClass(d, last_block=start)
    d.block_scanner.one_block_per_run = single_block
    d.block_scanner.allow_jumps = True

    # Just to check stability
    user_counter = UserCounterMiddleware(d)
    d.block_scanner.add_subscriber(user_counter)

    # Extract ThorTx from BlockResult
    native_action_extractor = SwapExtractorBlock(d)
    native_action_extractor.dbg_ignore_finished_status = True

    if tx_id:
        native_action_extractor.dbg_open_file(f'../temp/txs/{tx_id}.txt')
        native_action_extractor.dbg_watch_swap_id = tx_id

        # db = native_action_extractor._db
        # await db.backup('../temp/ev_db_backup_everything.json')

    d.block_scanner.add_subscriber(native_action_extractor)

    profit_calc = StreamingSwapVsCexProfitCalculator(d)
    native_action_extractor.add_subscriber(profit_calc)

    # Enrich with aggregator data
    aggregator = AggregatorDataExtractor(d)
    profit_calc.add_subscriber(aggregator)

    # Volume filler (important)
    volume_filler = VolumeFillerUpdater(d)
    aggregator.add_subscriber(volume_filler)

    # Just to check stability
    d.dex_analytics = DexAnalyticsCollector(d)
    aggregator.add_subscriber(d.dex_analytics)

    # Just to check stability
    volume_filler.add_subscriber(d.volume_recorder)
    volume_filler.add_subscriber(d.tx_count_recorder)

    # # Just to check stability: DEX reports
    dex_report_notifier = DexReportNotifier(d, d.dex_analytics)
    volume_filler.add_subscriber(dex_report_notifier)
    dex_report_notifier.add_subscriber(d.alert_presenter)

    # Swap notifier (when it finishes)
    curve_pts = d.cfg.get_pure('tx.curve', default=DepthCurve.DEFAULT_TX_VS_DEPTH_CURVE)
    curve = DepthCurve(curve_pts)

    swap_notifier_tx = SwapTxNotifier(d, d.cfg.tx.swap, curve=curve)
    # if tx_id:
    #     await swap_notifier_tx.deduplicator.forget(tx_id)

    swap_notifier_tx.dbg_evaluate_curve_for_pools()
    volume_filler.add_subscriber(swap_notifier_tx)
    swap_notifier_tx.add_subscriber(d.alert_presenter)

    # When SS starts we do notify as well
    stream_swap_notifier = StreamingSwapStartTxNotifier(d)
    stream_swap_notifier.check_unique = False
    d.block_scanner.add_subscriber(stream_swap_notifier)
    stream_swap_notifier.add_subscriber(d.alert_presenter)

    # Run all together
    if single_block:
        await d.block_scanner.run_once()
    else:
        while True:
            await d.block_scanner.run()
            await asyncio.sleep(5.9)


async def demo_search_for_deposit_streaming_synth(app):
    tx_fetcher = TxFetcher(app.deps, tx_types=(ActionType.SWAP,))
    txs = await tx_fetcher.fetch_one_batch(tx_types=tx_fetcher.tx_types)
    next_token = txs.next_page_token

    for page in range(1000):
        txs = await tx_fetcher.fetch_one_batch(next_page_token=next_token)
        next_token = txs.next_page_token

        for tx in txs.txs:
            if not tx.meta_swap:
                continue
            tx: ThorAction
            if Asset(tx.first_input_tx.first_asset).is_synth:
                if tx.memo.is_streaming:
                    sep('BINGO')
                    print(tx)


async def debug_tx_records(app: LpAppFramework, tx_id):
    ev_db = EventDatabase(app.deps.db)

    props = await ev_db.read_tx_status(tx_id)
    sep('swap')
    print(props)

    sep('tx')
    tx = props.build_action()
    print(tx)


async def debug_cex_profit_calc(app: LpAppFramework, tx_id):
    d = app.deps
    native_action_extractor = SwapExtractorBlock(d)

    tx = await native_action_extractor.find_tx(tx_id)
    if not tx:
        raise Exception(f'TX {tx_id} not found')

    volume_filler = VolumeFillerUpdater(d)

    profit_calc = StreamingSwapVsCexProfitCalculator(d)
    volume_filler.add_subscriber(profit_calc)

    swap_notifier_tx = SwapTxNotifier(d, d.cfg.tx.swap, curve=DepthCurve.DEFAULT_TX_VS_DEPTH_CURVE)
    swap_notifier_tx.no_repeat_protection = False
    swap_notifier_tx.curve_mult = 0.00001
    volume_filler.add_subscriber(swap_notifier_tx)

    swap_notifier_tx.add_subscriber(d.alert_presenter)

    # push it through the pipeline
    await volume_filler.on_data(None, [tx])

    await asyncio.sleep(5.0)


async def debug_cex_profit_calc_binance(app: LpAppFramework):
    profit_calc = StreamingSwapVsCexProfitCalculator(app.deps)

    btc = Asset.from_string('BTC.BTC')
    bnb = Asset.from_string('BNB.BNB')

    result = await profit_calc.binance_query(btc, bnb, 10)
    print(f'10 BTC => {result} BNB')

    result = await profit_calc.binance_query(bnb, btc, 10)
    print(f'10 BNB => {result} BTC')

    result = await profit_calc.binance_query(btc, AssetRUNE, 100)
    print(f'100 BTC => {result} RUNE')

    # print(await profit_calc.binance_get_order_book_cached('BTC', 'BNB'))


async def debug_tx_status(app):
    tx_st = await app.deps.thor_connector.query_tx_status(
        'EDF8885C62DA1814E1C0AB2FBA2F9E2BDA857FBCFEDA8CE27CD95C5A52C7597F')
    print(tx_st)


async def run():
    app = LpAppFramework()
    async with app(brief=True):
        print('start!')

        await app.deps.pool_fetcher.run_once()

        setup_logs(logging.DEBUG)

        # await debug_full_pipeline(app)

        # await debug_fetch_ss(app)
        # await debug_block_analyse(app, block=17361911)
        # await debug_full_pipeline(app, start=16387377, single_block=True,
        #                           tx_id='BE7B085E50DE86CD9BD8959ABF3EA924AC60302330888D484219B8B7385F7B1D')
        # await debug_tx_records(app, 'E8766E3D825A7BFD755ECA14454256CA25980F8B4BA1C9DCD64ABCE4904F033D')

        await debug_tx_records(app, '62065183022E32395A1538DE9AE28CCCD81247327971990D8A57FD88BE2594EC')

        # await debug_full_pipeline(
        #     app,
        #     start=16151780,
        #     # tx_id='696A2C031B2BCB73C6A78A297F30B5A33A91BB754C564F10AA589E089F05D573',
        #     single_block=False
        # )

        # ------------------- trade to trade no stream -------------------
        # await debug_full_pipeline(
        #     app,
        #     start=16908330,
        #     tx_id='BAB65D6A6A2D7AC127FDF36DF2B1219AC5F44732804848DB4FCEFC72AD5BCE77',
        #     single_block=True
        # )

        # ------------------- trade to trade with stream -------------------
        # await debug_full_pipeline(
        #     app,
        #     start=16908744 - 1,
        #     tx_id='4824290D3C7AE55F9915D4F0FEC46C93BB87604BD403649AD5BA208940218522',
        #     single_block=False
        # )

        # await debug_full_pipeline(
        #     app, start=12802333,
        #     tx_id='2065AD2148F242D59DEE34890022A2264C9B04C2297E04295BB118E29A995E05')

        # await debug_full_pipeline(
        #     app, start=12802040,
        #     tx_id='63218D1F853AEB534B3469C4E0236F43E04BFEE99832DF124425454B8DB1528E')

        # await debug_detect_start_on_deposit_rune(app)
        # await debug_detect_start_on_external_tx(app)

        # await debug_cex_profit_calc(app, '2065AD2148F242D59DEE34890022A2264C9B04C2297E04295BB118E29A995E05')
        # await debug_cex_profit_calc_binance(app)


if __name__ == '__main__':
    asyncio.run(run())
