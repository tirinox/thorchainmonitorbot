import asyncio

from jobs.fetch.stream_watchlist import StreamingSwapStartDetectorFromList, StreamingSwapWatchListFetcher
from jobs.scanner.scan_cache import BlockScannerCached
from jobs.scanner.swap_start_detector import SwapStartDetectorFromBlock
from lib.date_utils import parse_timespan_to_seconds, seconds_human
from notify.public.s_swap_notify import StreamingSwapStartTxNotifier
from tools.lib.lp_common import LpAppFramework, Receiver


TARGET_OBSERVED_TX_ID = '54F2B5075E6CAA7B2D3363A77C3384CAF8B9C3C448B8C04E1C0409016CAD6C2F'
TARGET_BLOCK_NO = 26101907


def dbg_print_swap_start_pipeline():
    print('\n=== Swap-start detector pipeline ===')
    print('1) Block path: THORNode block -> BlockScanner.fetch_one_block(height)')
    print('2) BlockResult parses MsgObservedTxQuorum / MsgDeposit messages')
    print('3) SwapStartDetectorFromBlock.detect_swaps(block, price_holder)')
    print('4) For observed inbound txs: obsTx -> ThorObservedTx -> AlertSwapStart')
    print('5) StreamingSwapStartTxNotifier.is_swap_eligible(event)')
    print('6) If eligible: load quote/clout -> pass further to listeners')
    print('   If too old / duplicate / arb / too small: event is dropped\n')


async def dbg_run_continuous(app: LpAppFramework):
    d = app.deps

    d.block_scanner = BlockScannerCached(d)

    swap_start_detector = SwapStartDetectorFromBlock(d)
    d.block_scanner.add_subscriber(swap_start_detector)

    stream_swap_notifier = StreamingSwapStartTxNotifier(d)
    swap_start_detector.add_subscriber(stream_swap_notifier)
    stream_swap_notifier.add_subscriber(d.alert_presenter)

    await d.block_scanner.run()
    await asyncio.sleep(5.0)


async def dbg_run_specific_tx(app: LpAppFramework, tx_id: str):
    d = app.deps

    watchlist = StreamingSwapWatchListFetcher(d)
    s_swap = await watchlist.load_streaming_swap_details(tx_id)

    sssd = StreamingSwapStartDetectorFromList(d)
    sssd.add_subscriber(d.alert_presenter)
    ph = await d.pool_cache.get()
    # noinspection PyProtectedMember


    await sssd._handle_swap_start(s_swap, ph)

    await asyncio.sleep(5.0)


async def dbg_run_block_once(app: LpAppFramework, block_no: int = TARGET_BLOCK_NO,
                             target_tx_id: str = TARGET_OBSERVED_TX_ID,
                             max_age_override: str | None = None):
    d = app.deps
    dbg_print_swap_start_pipeline()

    # Redis-backed caching is handy when you restart the debugger often.
    scanner = BlockScannerCached(d)
    detector = SwapStartDetectorFromBlock(d)
    notifier = StreamingSwapStartTxNotifier(d)

    if max_age_override is not None:
        notifier.max_age_sec = parse_timespan_to_seconds(max_age_override)
        print(f'Overriding notifier.max_age_sec with {max_age_override} -> {notifier.max_age_sec} sec')

    debug_receiver = Receiver(tag='ALERT_PASSED_TO_NEXT_STAGE')
    notifier.add_subscriber(debug_receiver)

    print(f'Loading block #{block_no}...')
    block = await scanner.fetch_one_block(block_no)
    print(f'Loaded block #{block.block_no}: tx_count={len(block.txs)} observed_txs={len(block.all_observed_txs)}')

    target_observed = None
    for obs_tx in block.all_observed_txs:
        if obs_tx.tx_id == target_tx_id:
            target_observed = obs_tx
            break

    print(f'target_tx_id = {target_tx_id}')
    print(f'target_observed_found = {bool(target_observed)}')
    if target_observed:
        print(f'obs.block_height = {target_observed.block_height}')
        print(f'obs.finalise_height = {target_observed.finalise_height}')
        print(f'obs.memo = {target_observed.memo}')
        print(f'obs.is_inbound = {target_observed.is_inbound}')
    else:
        print('Target observed tx not found in this block.')
        return

    ph = await d.pool_cache.get()
    swap_events = await detector.detect_swaps(block, ph)
    print(f'detector.detect_swaps -> {len(swap_events)} events')

    target_event = None
    for event in swap_events:
        if event.tx_id == target_tx_id:
            target_event = event
            break

    print(f'target_event_found = {bool(target_event)}')
    if not target_event:
        print('Target event not produced by detector.')
        return

    print('--- AlertSwapStart built by detector ---')
    print(f'event.tx_id = {target_event.tx_id}')
    print(f'event.block_height = {target_event.block_height}')
    print(f'event.in_asset = {target_event.in_asset}')
    print(f'event.out_asset = {target_event.out_asset}')
    print(f'event.volume_usd = {target_event.volume_usd}')
    print(f'event.quantity = {target_event.quantity}')
    print(f'event.interval = {target_event.interval}')
    print(f'event.is_streaming = {target_event.is_streaming}')
    print(f'event.memo_str = {target_event.memo_str}')
    print(f'block.block_no = {block.block_no}')
    print(f'event.block_height != block.block_no -> {target_event.block_height != block.block_no}')

    current_thor_block = await d.last_block_cache.get_thor_block()
    print(f'current_thor_block = {current_thor_block}')
    if current_thor_block:
        block_gap = int(current_thor_block) - int(target_event.block_height)
        age_sec = block_gap * notifier.thor_block_time_sec
        print(f'block_gap_to_current = {block_gap}')
        print(f'event_age_sec = {age_sec}')
        print(f'event_age_human = {seconds_human(age_sec)}')

    print(f'notifier.max_age_sec = {notifier.max_age_sec}')
    print(f'notifier.max_age_human = {seconds_human(notifier.max_age_sec)}')

    eligible = await notifier.is_swap_eligible(target_event)
    print(f'notifier.is_swap_eligible(event) -> {eligible}')

    if eligible:
        print('Event is eligible, running notifier.on_data(...) once')
        await notifier.on_data(detector, target_event)
    else:
        print('Event is filtered out before notification. notifier.on_data(...) is intentionally skipped.')

    await asyncio.sleep(0.1)


async def run():
    app = LpAppFramework()
    async with app:
        # Alternative path: watchlist -> StreamingSwapStartDetectorFromList -> presenter
        # await dbg_run_specific_tx(app, TARGET_OBSERVED_TX_ID)

        # Main debugger entrypoint:
        # block scanner -> observed tx -> SwapStartDetectorFromBlock -> StreamingSwapStartTxNotifier
        await dbg_run_block_once(app, TARGET_BLOCK_NO, TARGET_OBSERVED_TX_ID, max_age_override='2d')


if __name__ == '__main__':
    asyncio.run(run())
