import asyncio
import json
import logging
from pathlib import Path

from jobs.scanner.scan_cache import BlockScannerCached
from jobs.scanner.transfer_detector import RuneTransferDetector
from jobs.transfer_recorder import RuneTransferRecorder
from lib.constants import THOR_BLOCK_TIME
from lib.date_utils import DAY
from lib.utils import parallel_run_in_groups
from models.transfer import AlertRuneTransferStats
from notify.public.cex_flow import CEXFlowRecorder
from notify.public.transfer_notify import RuneMoveNotifier
from tools.lib.lp_common import LpAppFramework

DEMO_DIR = Path(__file__).parents[2] / 'renderer' / 'demo'


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
                await transfer_detector.on_data(sender=None, data=block_result)
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


async def dbg_transfer_stats_send(app: LpAppFramework, days: int = 14):
    """
    Build the RUNE transfer stats infographic from live Redis data and post it
    to the public channels via alert_presenter (same path as the scheduled job).
    """
    d = app.deps
    recorder = RuneTransferRecorder(d)
    summary = await recorder.get_summary(days=days)

    if not summary.get('transfer_count'):
        print('No RUNE transfer data in Redis yet — run the scanner first.')
        return

    usd_per_rune = await d.pool_cache.get_usd_per_rune()
    data = AlertRuneTransferStats.from_summary(summary, usd_per_rune=usd_per_rune)

    print(
        f'Sending RUNE transfer stats infographic\n'
        f'  period   : {data.period_days}d  ({data.start_date} – {data.end_date})\n'
        f'  volume   : {data.volume_rune:,.0f} RUNE\n'
        f'  cex in   : {data.cex_inflow_rune:,.0f} RUNE  ({data.cex_inflow_count} deposits)\n'
        f'  cex out  : {data.cex_outflow_rune:,.0f} RUNE  ({data.cex_outflow_count} withdrawals)\n'
        f'  net flow : {data.cex_netflow_rune:+,.0f} RUNE\n'
        f'  usd/rune : ${usd_per_rune:.4f}'
    )

    await d.alert_presenter.handle_data(data)
    print('Infographic sent — waiting for delivery…')
    await asyncio.sleep(5)


async def run():
    app = LpAppFramework(log_level=logging.INFO)
    async with app:
        await dbg_transfer_record_from_past(app, days=14)
        # await dbg_transfer_stats_last_data(app)
        # await dbg_transfer_stats_dump_demo(app)
        # await dbg_transfer_stats_send(app)


if __name__ == '__main__':
    asyncio.run(run())

