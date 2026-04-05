import asyncio
import json
from pathlib import Path
from typing import Any

from jobs.limit_recorder import LimitSwapStatsRecorder
from jobs.scanner.block_result import BlockResult
from jobs.scanner.limit_detector import LimitSwapDetector, LimitSwapBlockUpdate
from jobs.scanner.scan_cache import BlockScannerCached
from lib.delegates import INotified, WithDelegates
from lib.texts import sep
from lib.utils import recursive_asdict, say
from tools.lib.lp_common import LpAppFramework

DEMO_DIR = Path(__file__).parents[2] / 'renderer' / 'demo'


class PrintDetectedLimitSwapInfo(INotified):
    @staticmethod
    def _shorten(text: str, max_len: int = 160) -> str:
        text = str(text or '')
        return text if len(text) <= max_len else f'{text[:max_len - 3]}...'

    @staticmethod
    def _event_txid(ev) -> str:
        return str(ev.get('txid') or ev.get('id') or ev.get('in_tx_id') or '')

    @staticmethod
    def _announcement(update: LimitSwapBlockUpdate) -> str:
        parts = []
        if update.new_opened_limit_swaps:
            parts.append(f'{len(update.new_opened_limit_swaps)} opened')
        if update.closed_limit_swaps:
            parts.append(f'{len(update.closed_limit_swaps)} closed')
        if update.partial_swaps:
            parts.append(f'{len(update.partial_swaps)} partial')
        parts_str = ', '.join(parts)
        return f'Limit swap event in block {update.block_no}. {parts_str}.'

    async def on_data(self, sender, update: LimitSwapBlockUpdate):
        sep(f'Limit swap update @ block {update.block_no}')

        if update.new_opened_limit_swaps:
            print(f'New limit swaps: {len(update.new_opened_limit_swaps)}')
            for tx in update.new_opened_limit_swaps:
                print(
                    f'  OPEN   tx={tx.tx_id} '
                    f'signer={tx.trader or "?"} '
                    f'memo={self._shorten(tx.memo)}'
                )

        if update.closed_limit_swaps:
            print(f'Closed limit swaps: {len(update.closed_limit_swaps)}')
            for closed in update.closed_limit_swaps:
                ev = closed.event
                print(
                    f'  CLOSE  txid={closed.txid or self._event_txid(ev) or "?"} '
                    f'reason={self._shorten(closed.reason or ev.get("reason") or "") or "?"} '
                    f'memo={self._shorten(ev.memo)}'
                )

        if update.partial_swaps:
            print(f'Partial swap fills: {len(update.partial_swaps)}')
            for ev in update.partial_swaps:
                print(
                    f'  PARTIAL txid={self._event_txid(ev) or "?"} '
                    f'asset={ev.asset or "?"} '
                    f'amount={ev.amount or 0} '
                    f'memo={self._shorten(ev.memo)}'
                )

        await say(self._announcement(update))


class PrimitiveLimitMemoSubstringDetector(INotified, WithDelegates):
    TARGET_SUBSTRING = '=<:'
    MAX_PRINTED_MATCHES = 20

    def __init__(self):
        super().__init__()

    @staticmethod
    def _shorten(text: str, max_len: int = 200) -> str:
        text = str(text or '')
        return text if len(text) <= max_len else f'{text[:max_len - 3]}...'

    @classmethod
    def _scan_strings(cls, value: Any, path: str = 'block'):
        if isinstance(value, str):
            if cls.TARGET_SUBSTRING in value:
                yield path, value
            return

        if isinstance(value, dict):
            for key, inner_value in value.items():
                yield from cls._scan_strings(inner_value, f'{path}.{key}')
            return

        if isinstance(value, (list, tuple, set)):
            for index, inner_value in enumerate(value):
                yield from cls._scan_strings(inner_value, f'{path}[{index}]')

    @classmethod
    def _announcement(cls, block_no: int, matches: list[tuple[str, str]]) -> str:
        return (
            f'Primitive detector found {len(matches)} occurrences of '
            f'{cls.TARGET_SUBSTRING} in block {block_no}.'
        )

    async def on_data(self, sender, block: BlockResult):
        plain_block = recursive_asdict(block, add_properties=True, handle_datetime=True)
        matches = list(self._scan_strings(plain_block))

        if matches:
            sep(f'Primitive limit substring detector @ block {block.block_no}')
            print(self._announcement(block.block_no, matches))

            for path, value in matches[:self.MAX_PRINTED_MATCHES]:
                print(f'  MATCH  path={path} value={self._shorten(value)}')

            skipped = len(matches) - self.MAX_PRINTED_MATCHES
            if skipped > 0:
                print(f'  ... and {skipped} more matches')

            await say(self._announcement(block.block_no, matches))

        await self.pass_data_to_listeners(block)


async def dbg_limit_detector_continuous(app: LpAppFramework, last_block=0):
    d = app.deps
    if not last_block:
        last_block = await d.last_block_cache.get_thor_block()
        last_block -= 50000
        # last_block = 24802335
    block_scanner = BlockScannerCached(d, last_block=last_block)

    primitive_detector = PrimitiveLimitMemoSubstringDetector()
    limit_swap_detector = LimitSwapDetector(d)
    block_scanner.add_subscriber(primitive_detector)
    primitive_detector.add_subscriber(limit_swap_detector)
    limit_swap_detector.add_subscriber(PrintDetectedLimitSwapInfo())

    limit_swap_recorder = LimitSwapStatsRecorder(d)
    limit_swap_detector.add_subscriber(limit_swap_recorder)

    await block_scanner.run()


async def dbg_limit_last_data(app: LpAppFramework, days: int = 14):
    d = app.deps
    recorder = LimitSwapStatsRecorder(d)

    daily = await recorder.get_daily_data(days=2)
    summary = await recorder.get_summary(days=days)

    latest = daily[-1] if daily else {}

    print('Latest daily limit-swap data:')
    print(json.dumps(latest, indent=2, sort_keys=True))
    print()
    print(f'Limit-swap summary for last {days} days:')
    print(json.dumps(summary, indent=2, sort_keys=True))


async def dbg_limit_infographic_data(app: LpAppFramework, days: int = 7):
    """Dump limit-swap infographic data to renderer/demo/limit_swap_stats.json."""
    recorder = LimitSwapStatsRecorder(app.deps)
    data = await recorder.get_infographic_data(days=days)

    output = {
        'template_name': 'limit_swap_stats.jinja2',
        'parameters': data.to_dict(),
    }

    out_path = DEMO_DIR / 'limit_swap_stats.json'
    out_path.write_text(json.dumps(output, indent=2, sort_keys=True))
    print(f'Written to {out_path}')
    print(json.dumps(output, indent=2, sort_keys=True))


async def dbg_limit_infographic_send(app: LpAppFramework, days: int = 7):
    """Build the latest limit-swap infographic and send it via the alert presenter."""
    recorder = LimitSwapStatsRecorder(app.deps)
    data = await recorder.get_infographic_data(days=days)

    if not data.total.opened_count and not data.open_orders.total_count:
        print('No limit swap data available.')
        return

    print(f'Sending limit-swap infographic: {data}')
    await app.deps.alert_presenter.handle_data(data)
    print('Limit-swap infographic sent.')
    await asyncio.sleep(5)  # Give some time for the alert to be processed before exiting


async def run():
    app = LpAppFramework()
    async with app:
        await dbg_limit_detector_continuous(app, last_block=25588679)
        # await dbg_limit_detector_continuous(app)
        # await dbg_limit_last_data(app)
        # await dbg_limit_infographic_send(app)


if __name__ == '__main__':
    asyncio.run(run())
