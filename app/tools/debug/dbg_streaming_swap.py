import asyncio
from pprint import pprint

from services.jobs.fetch.native_scan import NativeScannerBlock
from services.jobs.fetch.streaming_swaps import StreamingSwapFechter
from services.jobs.native_actions import NativeActionExtractor
from services.jobs.user_counter import UserCounter
from services.jobs.volume_filler import VolumeFillerUpdater
from services.jobs.volume_recorder import VolumeRecorder
from services.lib.money import DepthCurve
from services.lib.w3.aggregator import AggregatorDataExtractor
from services.lib.w3.dex_analytics import DexAnalyticsCollector
from services.notify.types.dex_report_notify import DexReportNotifier
from services.notify.types.tx_notify import SwapTxNotifier
from tools.lib.lp_common import LpAppFramework

SS_EXAMPLE = '75327336C1EC3FE39D1DECB06C5F05756FAA5C28E0ACC777239F98D7F2903589'
SS_EXAMPLE_BLOCK = 12079656


# Memo:  =:ETH.THOR:0x8d2e7cab1747f98a7e1fa767c9ef62132e4c31db:139524325459200/9/99:t:30
# Mdg: https://midgard.ninerealms.com/v2/actions?txid=75327336C1EC3FE39D1DECB06C5F05756FAA5C28E0ACC777239F98D7F2903589
# VB: https://viewblock.io/thorchain/tx/75327336C1EC3FE39D1DECB06C5F05756FAA5C28E0ACC777239F98D7F2903589
# Inb: https://thornode.ninerealms.com/thorchain/tx/75327336C1EC3FE39D1DECB06C5F05756FAA5C28E0ACC777239F98D7F2903589
# Block: min = 12079656
# Block outbound : 17879640, finalized 12081263
# Block failed sub swap? 12080322
#


async def debug_fetch_ss(app: LpAppFramework):
    ssf = StreamingSwapFechter(app.deps)
    data = await ssf.run_once()
    print(data)


async def debug_block_analyse(app: LpAppFramework):
    scanner = NativeScannerBlock(app.deps)
    # await scanner.run()
    blk = await scanner.fetch_one_block(12080538)
    pprint(blk)

    naex = NativeActionExtractor(app.deps)
    actions = await naex.on_data(None, blk)
    print(actions)

    """
    Double swap. BTC => RUNE
    [DecodedEvent(type='swap', attributes=
    {'pool': 'BTC.BTC', 'swap_target': '0', 'swap_slip': '1', 'liquidity_fee': '11243951', 
    'liquidity_fee_in_rune': '11243951', 'emit_asset': '138462176483 THOR.RUNE', 
    'streaming_swap_quantity': '9', 'streaming_swap_count': '9', 
    'id': '026170F3A6E8EA8A9BA1DDBB106536390C086B64D8E157F31E65789A31841284', 
    'chain': 'BTC', 'from': 'bc1qhqrv445ynkzqw8dwllycwpespg4cwhc86vv6ar', 
    'to': 'bc1q7dntvsztw8pyul7904cstg9rs50dv96r787uym', 'coin': '6314336 BTC.BTC', 
    'amount': 6314336, 'asset': 'BTC.BTC', 
    'memo': '=:n:bnb1jer9yxcdpmrsy773z4r5kkak9xk7gpktfa6wx8:6904532050/9/9:t:30'}), """

    """
    The second part is RUNE => BNB
    
    DecodedEvent(type='swap', 
    attributes={'pool': 'BNB.BNB', 'swap_target': '742719800', 'swap_slip': '6', 'liquidity_fee': '426632', 
    'liquidity_fee_in_rune': '76713295', 'emit_asset': '769187667 BNB.BNB', 'streaming_swap_quantity': '9',
     'streaming_swap_count': '9', 'id': '026170F3A6E8EA8A9BA1DDBB106536390C086B64D8E157F31E65789A31841284', 
     'chain': 'BTC', 'from': 'bc1qhqrv445ynkzqw8dwllycwpespg4cwhc86vv6ar', 
     'to': 'bc1q7dntvsztw8pyul7904cstg9rs50dv96r787uym', 'coin': '138462176483 THOR.RUNE', 
     'amount': 138462176483, 'asset': 'THOR.RUNE', 
     'memo': '=:n:bnb1jer9yxcdpmrsy773z4r5kkak9xk7gpktfa6wx8:6904532050/9/9:t:30'})
    """

    """
    streaming_swap desc:
    
    DecodedEvent(type='streaming_swap', 
    attributes={'tx_id': '026170F3A6E8EA8A9BA1DDBB106536390C086B64D8E157F31E65789A31841284', 'interval': '9', 
    'quantity': '9', 'count': '9', 'last_height': '12132219', 'deposit': '56829000 BTC.BTC', 'in': '56829000 BTC.BTC', 
    'out': '6930999917 BNB.BNB', 'failed_swaps': b'', 'failed_swap_reasons': b''}), """


async def debug_full_pipeline(app, start=None):
    d = app.deps
    d.block_scanner = NativeScannerBlock(d, last_block=start)
    action_extractor = NativeActionExtractor(app.deps)
    d.block_scanner.add_subscriber(action_extractor)

    user_counter = UserCounter(d)
    d.block_scanner.add_subscriber(user_counter)

    aggregator = AggregatorDataExtractor(d)

    native_action_extractor = NativeActionExtractor(d)
    d.block_scanner.add_subscriber(native_action_extractor)
    native_action_extractor.add_subscriber(aggregator)

    volume_filler = VolumeFillerUpdater(d)
    aggregator.add_subscriber(volume_filler)

    d.dex_analytics = DexAnalyticsCollector(d)
    aggregator.add_subscriber(d.dex_analytics)

    d.volume_recorder = VolumeRecorder(d)
    volume_filler.add_subscriber(d.volume_recorder)

    if d.cfg.tx.dex_aggregator_update.get('enabled', True):
        dex_report_notifier = DexReportNotifier(d, d.dex_analytics)
        volume_filler.add_subscriber(dex_report_notifier)
        dex_report_notifier.add_subscriber(d.alert_presenter)

    curve_pts = d.cfg.get_pure('tx.curve', default=DepthCurve.DEFAULT_TX_VS_DEPTH_CURVE)
    curve = DepthCurve(curve_pts)

    swap_notifier_tx = SwapTxNotifier(d, d.cfg.tx.swap, curve=curve)
    volume_filler.add_subscriber(swap_notifier_tx)
    swap_notifier_tx.add_subscriber(d.alert_presenter)

    while True:
        await d.block_scanner.run()
        await asyncio.sleep(5.9)


async def run():
    app = LpAppFramework()
    async with app(brief=True):
        # await debug_fetch_ss(app)
        # await debug_block_analyse(app)
        await debug_full_pipeline(app)


if __name__ == '__main__':
    asyncio.run(run())
