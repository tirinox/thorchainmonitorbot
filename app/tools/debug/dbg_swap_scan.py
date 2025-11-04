import asyncio
import logging

from api.w3.aggregator import AggregatorDataExtractor
from jobs.scanner.block_result import BlockResult
from jobs.scanner.native_scan import BlockScanner
from jobs.scanner.scan_cache import BlockScannerCached
from jobs.scanner.swap_extractor import SwapExtractorBlock
from jobs.user_counter import UserCounterMiddleware
from jobs.volume_filler import VolumeFillerUpdater
from lib.delegates import INotified
from lib.money import DepthCurve
from lib.texts import sep
from lib.utils import say
from notify.public.tx_notify import SwapTxNotifier
from tools.lib.lp_common import LpAppFramework

BlockScannerClass = BlockScannerCached
print(BlockScannerClass, ' <= look!')
BlockScannerClass = BlockScanner


class FindOutbound(INotified):
    def __init__(self, in_tx_id=None):
        self.in_tx_id = in_tx_id

    async def on_data(self, sender, block: BlockResult):
        for ev in block.end_block_events:
            if ev.type == 'outbound':
                if ev.attrs['in_tx_id'] == self.in_tx_id:
                    sep()
                    print(ev)
                    await say('Outbound!')


async def debug_full_pipeline(app, start=None, tx_id=None, single_block=False, ignore_traders=False, from_db=False):
    d = app.deps

    if start is not None and start < 0:
        thor = await app.deps.last_block_cache.get_thor_block()
        assert thor > 0
        start = thor + start

    if tx_id and start is None:
        tx = await app.deps.thor_connector.query_tx_details(tx_id)
        height = tx['consensus_height']
        start = height - 2
        print(f'TX {tx_id} is at height {height}, will start from {start}')

    if start != 0:
        print('Start from block:', start)

    # Block scanner: the source of the river
    d.block_scanner = BlockScannerClass(d, last_block=start)
    d.block_scanner.initial_sleep = 0.1
    d.block_scanner.one_block_per_run = single_block
    d.block_scanner.allow_jumps = True

    d.block_scanner.add_subscriber(FindOutbound(tx_id))

    # Just to check stability
    user_counter = UserCounterMiddleware(d)
    d.block_scanner.add_subscriber(user_counter)

    # Extract ThorTx from BlockResult
    native_action_extractor = SwapExtractorBlock(d)
    native_action_extractor.dbg_ignore_finished_status = True

    if tx_id:
        native_action_extractor.dbg_watch_swap_id = tx_id

    d.block_scanner.add_subscriber(native_action_extractor)

    # Enrich with aggregator data
    aggregator = AggregatorDataExtractor(d)
    native_action_extractor.add_subscriber(aggregator)

    # Volume filler (important)
    volume_filler = VolumeFillerUpdater(d)
    aggregator.add_subscriber(volume_filler)

    # Just to check stability
    volume_filler.add_subscriber(d.volume_recorder)
    volume_filler.add_subscriber(d.tx_count_recorder)

    # Swap notifier (when it finishes)
    curve_pts = d.cfg.get_pure('tx.curve', default=DepthCurve.DEFAULT_TX_VS_DEPTH_CURVE)
    curve = DepthCurve(curve_pts)

    swap_notifier_tx = SwapTxNotifier(d, d.cfg.tx.swap, curve=curve)
    swap_notifier_tx.no_repeat_protection = False
    swap_notifier_tx.curve_mult = 0.0001
    swap_notifier_tx.dbg_ignore_traders = ignore_traders
    swap_notifier_tx.hide_arb_bots = False
    if tx_id:
        swap_notifier_tx.dbg_just_pass_only_tx_id = tx_id

    ph = await d.pool_cache.get()
    swap_notifier_tx.dbg_evaluate_curve_for_pools(ph)
    volume_filler.add_subscriber(swap_notifier_tx)
    swap_notifier_tx.add_subscriber(d.alert_presenter)

    # Run all together
    if from_db and tx_id:
        tx = await native_action_extractor.build_tx_from_database(tx_id)
        await native_action_extractor.pass_data_to_listeners([tx])
        await asyncio.sleep(4.0)
    elif single_block:
        await d.block_scanner.run_once()
        await asyncio.sleep(10.0)
    else:
        while True:
            await d.block_scanner.run()
            await asyncio.sleep(5.9)


async def dbg_one_finished_swap(app, tx_id):
    native_action_extractor = SwapExtractorBlock(app.deps)
    tx = await native_action_extractor.build_tx_from_database(tx_id)
    print(tx)


async def run():
    app = LpAppFramework(log_level=logging.DEBUG)
    async with app(brief=True):
        # out_asset is turned out "secured" but it is not. investigate!
        # await dbg_one_finished_swap(app, "59E9DEA85C268338266D76E872DF9D07DB362FB2C06AB34D3AA7F65FF4E79757")
        # await dbg_one_finished_swap(app, "D07FE81C65120782E47B729971DC9ADD5736AC9420A5FC0DA63DBCAC3BA93626")
        await dbg_one_finished_swap(app, "76657D59BCCC1E2B8C3B641C043045C9459DB1D492B12BFCC2682AA9BAAE0923")

        # issue: when finalized, the rune outbound is sent, and only after decent delay, there goes L1 outbound
        # await debug_full_pipeline(app, ignore_traders=True,
        #                           tx_id="97C2DAF7AD2A43BF4CC822A873C980FAF939719361DBD24641368EF32D9D5C27")
        #
        # await debug_full_pipeline(
        #     app,
        #     # start=19710746,
        #     start=19952232 - 5,
        #     tx_id='970008DE50B175B88F97773999D659136108E67BCE982C2B8262E6AEE86EE0C0',
        #     single_block=False,
        #     ignore_traders=True,
        # )

        # await debug_full_pipeline(
        #     app, from_db=True,
        #     tx_id='EBE9E8DD73CCC2B144080A6233720E44CDE2C3DDE7D1A0A99D427C485C7D7CC0',
        #     # start=20059078 - 10,
        #     ignore_traders=True,
        # )

        # await debug_full_pipeline(app)


if __name__ == '__main__':
    asyncio.run(run())
