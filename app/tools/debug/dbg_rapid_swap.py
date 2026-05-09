import argparse
import asyncio
import logging

from jobs.rapid_recorder import RapidSwapRecorder
from jobs.scanner.block_result import BlockResult
from jobs.scanner.native_scan import BlockScanner
from lib.constants import THOR_BLOCK_TIME, thor_to_float
from lib.delegates import INotified
from lib.texts import sep
from lib.utils import say
from tools.lib.lp_common import LpAppFramework

DEFAULT_SLEEP_PERIOD = THOR_BLOCK_TIME * 0.99
DEFAULT_LOG_LEVEL = 'INFO'
SCANNER_ROLE = 'dbg_rapid_swap'


class RapidSwapDebugPrinter(INotified):
    def __init__(self, recorder: RapidSwapRecorder, speak=True):
        self.recorder = recorder
        self.speak = speak
        self._announced_batches = set()

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

    @classmethod
    def _announcement(cls, block_no: int, tx_id: str, swap_count: int) -> str:
        tx_short = cls._shorten(tx_id, max_len=12)
        return f'Rapid swap x {swap_count} in block {block_no} for {tx_short}'

    async def on_data(self, sender, block: BlockResult):
        rapid_candidates = self.recorder.collect_rapid_swap_candidates(block)
        if not rapid_candidates:
            return

        sep(f'Rapid swap candidates @ block {block.block_no}')
        print(
            f'Block #{block.block_no:,} contains {len(rapid_candidates)} rapid-swap tx candidate(s).'
        )

        for tx_id, swap_events in sorted(rapid_candidates.items(), key=lambda item: (-len(item[1]), item[0])):
            batch_key = self.recorder._dedup_key(block.block_no, tx_id)
            swap_count = len(swap_events)
            blocks_saved = max(0, swap_count - 1)
            trader = next((event.from_address for event in swap_events if event.from_address), '?')
            memo = next((event.memo for event in swap_events if event.memo), '')
            summary = (
                f'RAPID block={block.block_no} tx={tx_id} swaps={swap_count} '
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

            if self.speak and batch_key not in self._announced_batches:
                await say(self._announcement(block.block_no, tx_id, swap_count))
                self._announced_batches.add(batch_key)

        print()


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
    start_block: int | None = None,
    stop_block: int | None = None,
    sleep_period: float = DEFAULT_SLEEP_PERIOD,
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
    printer = RapidSwapDebugPrinter(recorder, speak=speak)
    scanner.add_subscriber(recorder)
    scanner.add_subscriber(printer)

    print('>>> Rapid swap debug scan')
    print(f'    current block : {current_block:,}')
    print(f'    start block   : {start_block:,}')
    print(f'    stop block    : {(f"{stop_block:,}" if stop_block is not None else "run forever")}')
    print(f'    sleep period  : {sleep_period:.2f} sec')
    print(f'    speak         : {speak}')
    print()

    while True:
        try:
            await scanner.run_once()
        except asyncio.CancelledError:
            print('Scanner stopped: stop block reached.')
            break

        if stop_block is not None and scanner.last_block >= stop_block + 1:
            print(f'Scanner finished at inclusive stop block #{stop_block:,}.')
            break

        if sleep_period > 0:
            await asyncio.sleep(sleep_period)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Scan THORChain blocks with the normal BlockScanner pipeline and shout when a rapid swap is found.',
    )
    parser.add_argument(
        '--start-block',
        type=int,
        default=None,
        help='First block to scan. Omit to start from the current tip. Negative values mean offset from current tip.',
    )
    parser.add_argument(
        '--stop-block',
        type=int,
        default=None,
        help='Inclusive last block to scan. Omit to keep following new blocks forever.',
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
        help='Disable macOS speech announcements.',
    )
    parser.add_argument(
        '--log-level',
        default=DEFAULT_LOG_LEVEL,
        help=f'Logging level for the app bootstrap. Default: {DEFAULT_LOG_LEVEL}.',
    )
    return parser


async def run(args=None):
    parser = build_arg_parser()
    args = parser.parse_args(args=args)

    log_level = getattr(logging, str(args.log_level).upper(), logging.INFO)

    app = LpAppFramework(log_level=log_level)
    async with app:
        await dbg_rapid_swap_continuous(
            app,
            start_block=args.start_block,
            stop_block=args.stop_block,
            sleep_period=float(args.sleep_period),
            speak=not args.no_say,
        )


if __name__ == '__main__':
    asyncio.run(run())

