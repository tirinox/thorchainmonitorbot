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
        thor = app.deps.last_block_store.thor
        assert thor > 0
        start = thor + start

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

    swap_notifier_tx.dbg_evaluate_curve_for_pools()
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


async def run():
    app = LpAppFramework(log_level=logging.DEBUG)
    async with app(brief=True):
        await app.deps.last_block_fetcher.run_once()
        await app.deps.pool_fetcher.run_once()

        await debug_full_pipeline(app, ignore_traders=True, start=-200)

        # await debug_full_pipeline(
        #     app,
        #     # start=19710746,
        #     start=19711750,
        #     tx_id='0F77D9743C8FE2557A2DBD48E59BBA1CAD9B9B771ED1111AB7E6632EEF1584FA',
        #     single_block=False,
        #     ignore_traders=True,
        # )

        await debug_full_pipeline(
            app, from_db=True,
            tx_id='0F77D9743C8FE2557A2DBD48E59BBA1CAD9B9B771ED1111AB7E6632EEF1584FA'
        )


if __name__ == '__main__':
    asyncio.run(run())
