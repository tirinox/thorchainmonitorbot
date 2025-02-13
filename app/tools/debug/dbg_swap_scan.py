import asyncio
import logging

from api.w3.aggregator import AggregatorDataExtractor
from jobs.scanner.native_scan import BlockScanner
from jobs.scanner.scan_cache import BlockScannerCached
from jobs.scanner.swap_extractor import SwapExtractorBlock
from jobs.user_counter import UserCounterMiddleware
from jobs.volume_filler import VolumeFillerUpdater
from lib.money import DepthCurve
from notify.public.tx_notify import SwapTxNotifier
from tools.lib.lp_common import LpAppFramework

BlockScannerClass = BlockScannerCached
print(BlockScannerClass, ' <= look!')
BlockScannerClass = BlockScanner


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

    swap_notifier_tx.dbg_evaluate_curve_for_pools()
    volume_filler.add_subscriber(swap_notifier_tx)
    swap_notifier_tx.add_subscriber(d.alert_presenter)

    # Run all together
    if single_block:
        await d.block_scanner.run_once()
        await asyncio.sleep(10.0)
    else:
        while True:
            await d.block_scanner.run()
            await asyncio.sleep(5.9)


async def run():
    app = LpAppFramework(log_level=logging.DEBUG)
    async with app(brief=True):
        await app.deps.pool_fetcher.run_once()

        await debug_full_pipeline(app)

        # await debug_full_pipeline(
        #     app,
        #     start=19667693,
        #     tx_id='696A2C031B2BCB73C6A78A297F30B5A33A91BB754C564F10AA589E089F05D573',
        #     single_block=True
        # )


if __name__ == '__main__':
    asyncio.run(run())
