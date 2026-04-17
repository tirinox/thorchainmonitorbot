import asyncio
import json
import logging
import random
from pathlib import Path

from jobs.scanner.scan_cache import BlockScannerCached
from jobs.scanner.transfer_detector import RuneTransferDetector
from jobs.transfer_recorder import RuneTransferRecorder
from lib.constants import THOR_BLOCK_TIME, RUNE_DENOM
from lib.date_utils import DAY, now_ts
from lib.utils import parallel_run_in_groups
from models.transfer import AlertRuneTransferStats, NativeTokenTransfer
from notify.public.cex_flow import CEXFlowRecorder
from notify.public.transfer_notify import RuneMoveNotifier
from tools.lib.lp_common import LpAppFramework

DEMO_DIR = Path(__file__).parents[2] / 'renderer' / 'demo'


def _build_fake_rune_transfer(rng: random.Random, cex_list: list[str], ts: float, idx: int) -> NativeTokenTransfer:
    cex_addr = rng.choice(cex_list)
    non_cex_addr = f'thor1debugfake{idx:02d}{rng.randrange(10_000, 99_999)}'
    amount = round(rng.uniform(750, 25_000), 2)
    direction = rng.choice(('deposit', 'withdrawal'))

    if direction == 'deposit':
        from_addr, to_addr = non_cex_addr, cex_addr
    else:
        from_addr, to_addr = cex_addr, non_cex_addr

    return NativeTokenTransfer(
        from_addr=from_addr,
        to_addr=to_addr,
        block=int(ts // THOR_BLOCK_TIME),
        tx_hash=f'debug-fake-rune-transfer-{idx:02d}',
        amount=amount,
        usd_per_asset=1.0,
        is_native=True,
        asset=RUNE_DENOM,
        comment='debug fake cex flow',
        memo='',
        block_ts=ts,
    )


async def main():
    app = LpAppFramework(log_level=logging.INFO)
    async with app:
        d = app.deps
        last_block = await d.last_block_cache.get_thor_block()
        last_block -= 10000
        d.block_scanner = BlockScannerCached(d, max_attempts=5, last_block=last_block)

        reserve_address = d.cfg.as_str('native_scanner.reserve_address')
        transfer_decoder = RuneTransferDetector(reserve_address)
        d.block_scanner.add_subscriber(transfer_decoder)

        if d.cfg.get('token_transfer.enabled', True):
            d.rune_move_notifier = RuneMoveNotifier(d)
            d.rune_move_notifier.min_usd_native = 10000
            d.rune_move_notifier.add_subscriber(d.alert_presenter)
            transfer_decoder.add_subscriber(d.rune_move_notifier)

        if d.cfg.get('token_transfer.flow_summary.enabled', True):
            cex_flow_notifier = CEXFlowRecorder(d)
            # cex_flow_notifier.summary_cd.cooldown = 10
            transfer_decoder.add_subscriber(cex_flow_notifier)

        await d.block_scanner.run()


# ── RuneTransfer stats debug helpers ──────────────────────────────────────────

async def dbg_transfer_record_from_past(app: LpAppFramework, days: int = 14, start_block: int = 0,
                                        stride: int = 10, concurrency: int = 8):
    """
    Replay historical blocks through RuneTransferDetector → RuneTransferRecorder
    to backfill the Redis DailyAccumulator for the given number of days.

    Mirrors dbg_vote_record_from_past: blocks are fetched independently at
    specific heights and processed in parallel groups, so backfilling is much
    faster than running BlockScannerCached sequentially.

    Parameters
    ----------
    days        : how many days back to start (ignored when start_block > 0)
    start_block : explicit starting block; 0 → auto-compute from `days`
    stride      : process every N-th block (default 10 — good balance between
                  speed and completeness; large transfers appear every few blocks)
    concurrency : max coroutines running simultaneously (default 8)
    """
    d = app.deps

    last_block = await d.last_block_cache.get_thor_block()

    if not start_block:
        start_block = last_block - int(days * DAY / THOR_BLOCK_TIME)

    total_blocks = last_block - start_block
    effective = total_blocks // stride

    print(
        f'Back-filling RUNE transfer stats:\n'
        f'  days to replay   : {days}\n'
        f'  start block      : {start_block}\n'
        f'  current block    : {last_block}\n'
        f'  stride           : every {stride} blocks\n'
        f'  blocks to process: ~{effective:,} (of {total_blocks:,} total)\n'
        f'  concurrency      : {concurrency}'
    )

    # Scanner is used only for fetch_one_block() + its built-in Redis caching.
    # We never call .run() on it.
    scanner = BlockScannerCached(d, last_block=start_block, stride=stride)

    reserve_address = d.cfg.as_str('native_scanner.reserve_address')
    transfer_detector = RuneTransferDetector(reserve_address)

    recorder = RuneTransferRecorder(d)
    transfer_detector.add_subscriber(recorder)

    async def process_one_block(block_no: int):
        try:
            block_result = await scanner.fetch_one_block(block_no)
            if block_result and not block_result.is_error:
                await transfer_detector.on_data(sender=None, block=block_result)
        except Exception as e:
            print(f'[Error] block {block_no}: {e}')

    tasks = [process_one_block(b) for b in range(start_block, last_block, stride)]
    await parallel_run_in_groups(tasks, concurrency, use_tqdm=True)

    summary = await recorder.get_summary(days=days)
    brief = {k: v for k, v in summary.items() if k != 'daily'}
    print('\nBack-fill complete. Accumulated summary:')
    print(json.dumps(brief, indent=2))

async def dbg_transfer_stats_last_data(app: LpAppFramework, days: int = 14):
    """Print the raw accumulated transfer stats from Redis."""
    recorder = RuneTransferRecorder(app.deps)

    daily = await recorder.get_daily_data(days=days)
    summary = await recorder.get_summary(days=days)

    latest = daily[-1] if daily else {}
    print('Latest daily RUNE transfer data:')
    print(json.dumps(latest, indent=2, sort_keys=True))
    print()
    print(f'Summary for last {days} days:')
    # exclude the big daily list for readability
    brief = {k: v for k, v in summary.items() if k != 'daily'}
    print(json.dumps(brief, indent=2, sort_keys=True))


async def dbg_transfer_stats_dump_demo(app: LpAppFramework, days: int = 14):
    """
    Pull live data from Redis and dump it to
    renderer/demo/rune_transfer_stats_live.json so the renderer dev-server
    can display it without a running bot.
    """
    recorder = RuneTransferRecorder(app.deps)
    summary = await recorder.get_summary(days=days)
    usd_per_rune = await app.deps.pool_cache.get_usd_per_rune()
    data = AlertRuneTransferStats.from_summary(summary, usd_per_rune=usd_per_rune)

    output = {
        'template_name': 'rune_transfer_stats.jinja2',
        'parameters': data.to_dict(),
    }

    out_path = DEMO_DIR / 'rune_transfer_stats_live.json'
    out_path.write_text(json.dumps(output, indent=2))
    print(f'Written to {out_path}')
    print(json.dumps(output, indent=2))


async def dbg_transfer_stats_fill_fake_data(app: LpAppFramework, days: int = 14, transfer_count: int = 8,
                                            clear_existing: bool = True):
    """
    Seed `RuneTransferRecorder` with synthetic RUNE transfers over the last `days` days.

    The generated transfers are split between CEX deposits and withdrawals, use
    the configured CEX list, and stay within the recorder's normal filtering
    rules so the infographic/debug output works exactly like real data.
    """
    if transfer_count < 5 or transfer_count > 10:
        raise ValueError('transfer_count should be between 5 and 10 for the debug helper')

    recorder = RuneTransferRecorder(app.deps)
    cex_list = sorted(recorder.cex_list)
    if not cex_list:
        raise ValueError('CEX list is empty; cannot seed fake transfer data')

    if clear_existing:
        await recorder.accumulator.clear()

    rng = random.Random(1337)
    base_end_ts = now_ts()

    day_offsets = sorted(rng.sample(range(days), transfer_count))
    transfers = []
    for idx, day_offset in enumerate(day_offsets, start=1):
        ts = base_end_ts - (days - 1 - day_offset) * DAY + rng.uniform(0, DAY - 1)
        transfers.append(_build_fake_rune_transfer(rng, cex_list, ts, idx))

    await recorder.on_data(sender=None, transfers=transfers)

    summary = await recorder.get_summary(days=days)
    brief = {k: v for k, v in summary.items() if k != 'daily'}
    print(f'Filled RuneTransferRecorder with {len(transfers)} fake transfers across the last {days} days.')
    print(json.dumps(brief, indent=2, sort_keys=True))
    return summary


async def dbg_transfer_stats_send(app: LpAppFramework):
    """
    Run the public `job_rune_cex_flow` job directly so the debug helper uses
    the same code path as the scheduled alert.
    """
    d = app.deps

    print('Running public `job_rune_cex_flow`...')
    await d.pub_alert_executor.job_rune_cex_flow()
    print('Infographic sent — waiting for delivery…')
    await asyncio.sleep(5)


async def run():
    app = LpAppFramework(log_level=logging.INFO)
    async with app:
        # await dbg_transfer_stats_fill_fake_data(app, days=14, transfer_count=8)
        # await dbg_transfer_record_from_past(app, days=6, stride=50, concurrency=16)
        # await dbg_transfer_stats_last_data(app)
        # await dbg_transfer_stats_dump_demo(app)
        await dbg_transfer_stats_send(app)
        # await dbg_transfer_stats_fill_fake_data(app, days=14, transfer_count=8, clear_existing=False)


if __name__ == '__main__':
    asyncio.run(run())

