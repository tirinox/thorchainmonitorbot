import asyncio

from services.jobs.scanner.event_db import EventDatabase
from services.jobs.scanner.native_scan import NativeScannerBlock
from services.jobs.user_counter import UserCounter
from services.jobs.volume_filler import VolumeFillerUpdater
from services.jobs.volume_recorder import VolumeRecorder
from services.lib.money import DepthCurve
from services.lib.texts import sep
from services.lib.w3.aggregator import AggregatorDataExtractor
from services.notify.types.tx_notify import SwapTxNotifier
from tools.lib.lp_common import LpAppFramework


async def debug_block_analyse(app: LpAppFramework):
    scanner = NativeScannerBlock(app.deps)
    # await scanner.run()
    blk = await scanner.fetch_one_block(12209517)
    sep()

    # naex = SwapExtractorBlock(app.deps)
    # actions = await naex.on_data(None, blk)
    # print(actions)


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
    # native_action_extractor = SwapExtractorBlock(d)
    # native_action_extractor.dbg_open_file(f'../temp/{tx_id}.txt')
    # if tx_id:
    #     native_action_extractor.dbg_watch_swap_id = tx_id
    #     native_action_extractor._db.dbg_only_tx_id = tx_id
    #
    # await native_action_extractor._db.backup('../temp/ev_db_backup_everything.json')
    # d.block_scanner.add_subscriber(native_action_extractor)

    # Enrich with aggregator data
    aggregator = AggregatorDataExtractor(d)
    # native_action_extractor.add_subscriber(aggregator)

    # Volume filler (important)
    volume_filler = VolumeFillerUpdater(d)
    aggregator.add_subscriber(volume_filler)

    # Just to check stability
    d.volume_recorder = VolumeRecorder(d)
    volume_filler.add_subscriber(d.volume_recorder)

    # Swap notifier (when it finishes)
    curve_pts = d.cfg.get_pure('tx.curve', default=DepthCurve.DEFAULT_TX_VS_DEPTH_CURVE)
    curve = DepthCurve(curve_pts)

    swap_notifier_tx = SwapTxNotifier(d, d.cfg.tx.swap, curve=curve)
    swap_notifier_tx.dbg_evaluate_curve_for_pools()
    volume_filler.add_subscriber(swap_notifier_tx)
    swap_notifier_tx.add_subscriber(d.alert_presenter)

    # When SS starts we do notify as well
    # stream_swap_notifier = StreamingSwapStartTxNotifier(d)
    # d.block_scanner.add_subscriber(stream_swap_notifier)
    # stream_swap_notifier.add_subscriber(d.alert_presenter)
    # await stream_swap_notifier.clear_seen_cache()

    # Run all together
    if single_block:
        await d.block_scanner.run_once()
    else:
        while True:
            await d.block_scanner.run()
            await asyncio.sleep(5.9)


async def debug_tx_records(app: LpAppFramework, tx_id):
    ev_db = EventDatabase(app.deps.db)

    props = await ev_db.read_tx_status(tx_id)
    sep('swap')
    print(props)

    sep('tx')
    tx = props.build_tx()
    print(tx)


async def run():
    app = LpAppFramework()
    async with app(brief=True):
        await app.deps.pool_fetcher.reload_global_pools()
        await app.deps.last_block_fetcher.run_once()

        await debug_tx_records(app, 'xxx')

        await debug_full_pipeline(
            app,
            start=123,
            # tx_id='xx',
            # single_block=True
        )


if __name__ == '__main__':
    asyncio.run(run())
