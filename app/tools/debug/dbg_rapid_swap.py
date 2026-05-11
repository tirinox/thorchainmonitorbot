import argparse
import asyncio
import logging
from pprint import pprint

from jobs.rapid_recorder import RapidSwapRecorder
from jobs.scanner.event_db import EventDatabase
from jobs.scanner.block_result import BlockResult
from jobs.scanner.native_scan import BlockScanner
from jobs.scanner.swap_props import group_rapid_swap_executions
from jobs.scanner.swap_extractor import SwapExtractorBlock
from lib.constants import THOR_BLOCK_TIME, thor_to_float
from lib.delegates import INotified
from lib.depcont import DepContainer
from lib.texts import sep
from lib.utils import say
from models.events import EventStreamingSwap, EventSwap, EventOutbound
from models.memo import ActionType
from tools.lib.lp_common import LpAppFramework

DEFAULT_SLEEP_PERIOD = THOR_BLOCK_TIME * 0.99
DEFAULT_LOG_LEVEL = 'INFO'
SCANNER_ROLE = 'dbg_rapid_swap'
DEFAULT_START_BLOCK = 26130215 - 1
DEFAULT_WATCH_TX_ID = '220DB364FB625F7570A7C1C5B56831A22F88405F3713453908EBFFD0C7A627C4'


class RapidSwapDebugPrinter(INotified):
    def __init__(self, recorder: RapidSwapRecorder, watch_tx_id: str = ''):
        self.recorder = recorder
        self.watch_tx_id = (watch_tx_id or '').upper()

    @staticmethod
    def _shorten(text: str, max_len: int = 180) -> str:
        text = str(text or '')
        return text if len(text) <= max_len else f'{text[:max_len - 3]}...'

    @staticmethod
    def _format_amount(amount: int) -> str:
        if not amount:
            return '0'
        return f'{thor_to_float(amount):,.8f}'

    @staticmethod
    def _streaming_suffix(swap_event) -> str:
        quantity = int(swap_event.streaming_swap_quantity or 0)
        count = int(swap_event.streaming_swap_count or 0)
        if quantity <= 0:
            return ''
        if count > 0:
            return f' stream={count}/{quantity}'
        return f' stream=0/{quantity}'

    async def on_data(self, sender, block: BlockResult):
        rapid_candidates = self.recorder.collect_rapid_swap_candidates(block)
        if self.watch_tx_id:
            rapid_candidates = {
                tx_id: swap_events
                for tx_id, swap_events in rapid_candidates.items()
                if str(tx_id).upper() == self.watch_tx_id
            }
        if not rapid_candidates:
            return

        sep(f'Rapid swap candidates @ block {block.block_no}')
        print(
            f'Block #{block.block_no:,} contains {len(rapid_candidates)} rapid-swap tx candidate(s).'
        )

        for tx_id, swap_events in sorted(rapid_candidates.items(), key=lambda item: (-len(item[1]), item[0])):
            execution_groups = group_rapid_swap_executions(swap_events)
            swap_count = len(execution_groups)
            raw_event_count = len(swap_events)
            blocks_saved = max(0, swap_count - 1)
            trader = next((event.from_address for event in swap_events if event.from_address), '?')
            memo = next((event.memo for event in swap_events if event.memo), '')
            summary = (
                f'RAPID block={block.block_no} tx={tx_id} swaps={swap_count} raw_events={raw_event_count} '
                f'blocks_saved={blocks_saved} trader={trader} memo={self._shorten(memo)}'
            )
            logging.warning(summary)
            print(summary)

            for index, swap_event in enumerate(swap_events, start=1):
                print(
                    f'  {index:02d}. pool={swap_event.pool or "?"} '
                    f'asset={swap_event.asset or "?"} '
                    f'amount={self._format_amount(swap_event.amount)} '
                    f'raw={swap_event.amount or 0} '
                    f'emit={swap_event.emit_asset or "?"}'
                    f'{self._streaming_suffix(swap_event)} '
                    f'memo={self._shorten(swap_event.memo)}'
                )

        print()


class RapidSwapCompletedDebugNotifier(INotified):
    def __init__(self, deps: DepContainer, speak=True, watch_tx_id: str = ''):
        self.speak = speak
        self._ev_db = EventDatabase(deps.db)
        self._announced_txs = set()
        self.watch_tx_id = (watch_tx_id or '').upper()
        self._watched_tx_completed = asyncio.Event()

    @property
    def watched_tx_completed(self) -> bool:
        return self._watched_tx_completed.is_set()

    async def on_data(self, sender, txs: list):
        announced = []

        for tx in txs:
            if not tx or not tx.is_of_type(ActionType.SWAP):
                continue

            if self.watch_tx_id and str(tx.tx_hash).upper() != self.watch_tx_id:
                continue

            self._watched_tx_completed.set()

            if tx.tx_hash in self._announced_txs:
                continue

            swap_props = await self._ev_db.read_tx_status(tx.tx_hash)
            if not swap_props:
                continue

            rapid_stats = swap_props.rapid_swap_stats
            if rapid_stats.blocks_saved <= 0:
                continue

            self._announced_txs.add(tx.tx_hash)
            announced.append(tx.tx_hash)
            summary = (
                f'RAPID FINISHED tx={tx.tx_hash} '
                f'blocks_saved={rapid_stats.blocks_saved} '
                f'total_swaps={rapid_stats.total_swaps} '
                f'distinct_blocks={rapid_stats.distinct_blocks}'
            )
            logging.warning(summary)
            print(summary)

            if self.speak:
                await say('rapid swap')

        return announced


async def resolve_start_block(app: LpAppFramework, start_block: int | None):
    current_block = await app.deps.last_block_cache.get_thor_block()

    if start_block is None:
        start_block = current_block
    elif start_block < 0:
        start_block = max(0, current_block + start_block)

    return current_block, int(start_block)


async def dbg_rapid_swap_continuous(
    app: LpAppFramework,
    *,
    start_block: int | None = DEFAULT_START_BLOCK,
    stop_block: int | None = None,
    sleep_period: float = DEFAULT_SLEEP_PERIOD,
    watch_tx_id: str = DEFAULT_WATCH_TX_ID,
    speak=True,
):
    d = app.deps
    current_block, start_block = await resolve_start_block(app, start_block)

    if stop_block is not None and stop_block < start_block:
        raise ValueError(f'stop_block must be >= start_block, got {start_block=} {stop_block=}')

    scanner = BlockScanner(
        d,
        sleep_period=sleep_period,
        last_block=start_block,
        role=SCANNER_ROLE,
    )
    scanner.initial_sleep = 0.0
    scanner.allow_jumps = True
    scanner.stop_block = int(stop_block) + 1 if stop_block is not None else 0

    recorder = RapidSwapRecorder(d)
    printer = RapidSwapDebugPrinter(recorder, watch_tx_id=watch_tx_id)
    extractor = SwapExtractorBlock(d)
    completed_notifier = RapidSwapCompletedDebugNotifier(d, speak=speak, watch_tx_id=watch_tx_id)
    scanner.add_subscriber(recorder)
    scanner.add_subscriber(printer)
    scanner.add_subscriber(extractor)
    extractor.add_subscriber(completed_notifier)

    print('>>> Rapid swap debug scan')
    print(f'    current block : {current_block:,}')
    print(f'    start block   : {start_block:,}')
    print(f'    stop block    : {(f"{stop_block:,}" if stop_block is not None else "run forever")}')
    print(f'    watch tx      : {watch_tx_id or "<any>"}')
    print(f'    sleep period  : {sleep_period:.2f} sec')
    print(f'    speak         : {speak}')
    print()

    while True:
        try:
            await scanner.run_once()
        except asyncio.CancelledError:
            print('Scanner stopped: stop block reached.')
            break

        if watch_tx_id and completed_notifier.watched_tx_completed:
            print(f'Watched tx completed: {watch_tx_id}')
            break

        if stop_block is not None and scanner.last_block >= stop_block + 1:
            print(f'Scanner finished at inclusive stop block #{stop_block:,}.')
            break

        if sleep_period > 0:
            await asyncio.sleep(sleep_period)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Scan THORChain blocks with rapid-swap candidate tracking plus the normal finished-swap extractor.',
    )
    parser.add_argument(
        '--start-block',
        type=int,
        default=DEFAULT_START_BLOCK,
        help='First block to scan. Default is the currently watched debug block. Negative values mean offset from current tip.',
    )
    parser.add_argument(
        '--stop-block',
        type=int,
        default=None,
        help='Inclusive last block to scan. Omit to keep scanning until the watched tx completes.',
    )
    parser.add_argument(
        '--tx-id',
        default=DEFAULT_WATCH_TX_ID,
        help='Only print/announce rapid-swap information for this inbound tx hash.',
    )
    parser.add_argument(
        '--sleep-period',
        type=float,
        default=DEFAULT_SLEEP_PERIOD,
        help=f'Sleep between scanner ticks in seconds. Default: {DEFAULT_SLEEP_PERIOD:.2f}.',
    )
    parser.add_argument(
        '--no-say',
        action='store_true',
        help='Disable the short "rapid swap" speech when a completed rapid swap is detected.',
    )
    parser.add_argument(
        '--log-level',
        default=DEFAULT_LOG_LEVEL,
        help=f'Logging level for the app bootstrap. Default: {DEFAULT_LOG_LEVEL}.',
    )
    return parser


async def dbg_print_tx_status(app, tx_id: str = DEFAULT_WATCH_TX_ID):
    ev_db = EventDatabase(app.deps.db)
    swap_props = await ev_db.read_tx_status(tx_id)

    print('=' * 120)
    print(f'TX STATUS DEBUG: {tx_id}')
    print('=' * 120)

    if not swap_props:
        print('No tx status found in EventDatabase.')
        return None

    print('\n--- attrs ---')
    pprint(dict(swap_props.attrs))

    print('\n--- derived flags ---')
    print(f'status            = {swap_props.status}')
    print(f'given_away        = {swap_props.given_away}')
    print(f'has_started       = {swap_props.has_started}')
    print(f'has_swaps         = {swap_props.has_swaps}')
    print(f'is_finished       = {swap_props.is_finished}')
    print(f'is_completed      = {swap_props.is_completed}')
    print(f'is_streaming      = {swap_props.is_streaming}')
    print(f'is_output_l1_asset= {swap_props.is_output_l1_asset}')
    print(f'is_output_trade   = {swap_props.is_output_trade}')
    print(f'from_address      = {swap_props.from_address}')
    print(f'in_coin           = {swap_props.in_coin}')

    try:
        rs = swap_props.rapid_swap_stats
        print('\n--- rapid swap stats ---')
        print(f'total_swaps       = {rs.total_swaps}')
        print(f'distinct_blocks   = {rs.distinct_blocks}')
        print(f'blocks_with_multi = {rs.blocks_with_multi}')
        print(f'blocks_saved      = {rs.blocks_saved}')
        print(f'streaming_qty     = {rs.streaming_swap_quantity}')
    except Exception as e:
        print(f'\nFailed to compute rapid_swap_stats: {e!r}')

    print('\n--- events ---')
    for i, ev in enumerate(swap_props.events, start=1):
        print(f'\n[{i:02d}] {ev.__class__.__name__}')

        if isinstance(ev, EventSwap):
            print(f'  height                 = {ev.height}')
            print(f'  tx_id                  = {ev.tx_id}')
            print(f'  pool                   = {ev.pool}')
            print(f'  asset                  = {ev.asset}')
            print(f'  amount                 = {ev.amount}')
            print(f'  emit_asset             = {ev.emit_asset}')
            print(f'  streaming_swap_count   = {ev.streaming_swap_count}')
            print(f'  streaming_swap_quantity= {ev.streaming_swap_quantity}')
            print(f'  memo                   = {ev.memo}')

        elif isinstance(ev, EventOutbound):
            print(f'  height     = {ev.height}')
            print(f'  tx_id      = {ev.tx_id}')
            print(f'  out_id     = {ev.out_id}')
            print(f'  chain      = {ev.chain}')
            print(f'  to_address = {ev.to_address}')
            print(f'  amount     = {ev.amount}')
            print(f'  asset      = {ev.asset}')
            print(f'  memo       = {ev.memo}')

        elif isinstance(ev, EventStreamingSwap):
            print(f'  height       = {ev.height}')
            print(f'  tx_id        = {ev.tx_id}')
            print(f'  quantity     = {ev.quantity}')
            print(f'  count        = {ev.count}')
            print(f'  last_height  = {ev.last_height}')
            print(f'  deposit      = {ev.deposit}')
            print(f'  in           = {ev.in_amt_str}')
            print(f'  out          = {ev.out_amt_str}')

        else:
            print(f'  raw = {ev}')

    print('\n--- outbounds gathered ---')
    for out in swap_props.gather_outbounds():
        print(out)

    print('=' * 120)
    return swap_props


async def run(args=None):
    parser = build_arg_parser()
    args = parser.parse_args(args=args)

    log_level = getattr(logging, str(args.log_level).upper(), logging.INFO)

    app = LpAppFramework(log_level=log_level)
    async with app:
        await dbg_print_tx_status(app, tx_id=args.tx_id)
        return
        await dbg_rapid_swap_continuous(
            app,
            start_block=args.start_block,
            stop_block=args.stop_block,
            sleep_period=float(args.sleep_period),
            watch_tx_id=str(args.tx_id or ''),
            speak=not args.no_say,
        )


if __name__ == '__main__':
    asyncio.run(run())

