import asyncio
import json
import logging
import os
import time
from datetime import datetime

from jobs.fetch.cached.wasm import WasmCache
from jobs.fetch.wasm_stats import WasmStatsBuilder
from jobs.scanner.block_result import BlockResult
from jobs.scanner.scan_cache import BlockScannerCached
from jobs.wasm_recorder import CosmWasmRecorder
from lib.date_utils import now_ts, DAY
from lib.delegates import INotified
from lib.texts import sep
from notify.pub_configure import PubAlertJobNames
from tools.lib.lp_common import LpAppFramework

DEMO_JSON_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '../../renderer/demo/app_layer_stats.json')
)


async def dbg_wasm_cache(app: LpAppFramework) -> WasmCache:
    """Load the WASM cache and print a full report including contract labels."""
    wasm_cache = WasmCache(app.deps.thor_connector, db=app.deps.db)

    sep()
    print(">>> First get() — may come from Redis or network...")
    t0 = time.perf_counter()
    stats = await wasm_cache.get()
    elapsed = time.perf_counter() - t0

    sep()
    print(f"Fetched in {elapsed:.2f}s")
    print(f"Total code variants     : {stats.total_codes}")
    print(f"Total contract instances: {stats.total_contracts}")

    for cs in stats.codes:
        sep()
        print(
            f"  code_id={cs.code_id:>4}  contracts={cs.contract_count:>5}"
            f"  creator={cs.creator[:20]}..."
            f"  hash={cs.data_hash[:12]}..."
        )
        for entry in cs.contracts:
            print(f"    {entry.address}  label={entry.label!r}")

    sep()
    print(">>> Redis TTL check...")
    r = await app.deps.db.get_redis()
    ttl = await r.ttl(WasmCache.REDIS_KEY)
    if ttl == -2:
        print("  Key not found in Redis.")
    elif ttl == -1:
        print("  Key exists in Redis but has no TTL (unexpected).")
    else:
        print(f"  Key '{WasmCache.REDIS_KEY}' TTL = {ttl}s "
              f"(~{ttl // 3600}h {(ttl % 3600) // 60}m remaining).")

    n_labels = await r.hlen(WasmCache.REDIS_LABELS_HASH)
    print(f"  Labels hash '{WasmCache.REDIS_LABELS_HASH}': {n_labels} entry(ies), no TTL.")

    sep()
    print(">>> get_label() convenience lookup...")
    if stats.all_contracts:
        addr = stats.all_contracts[0].address
        label = await wasm_cache.get_label(addr)
        print(f"  get_label({addr!r}) = {label!r}")

        wasm_cache._cache = None
        label2 = await wasm_cache.get_label(addr)
        print(f"  (no in-memory cache) get_label({addr!r}) = {label2!r}  [from Redis hash]")
    else:
        print("  (no contracts loaded)")

    sep()
    print(">>> New deployments in the last 7 days...")
    nd = await wasm_cache.count_new_deployments(days=7, last_block_cache=app.deps.last_block_cache)
    print(f"  {nd}")
    print(f"  New codes ({nd.new_codes_count}):")
    for cs in nd.new_codes:
        print(f"    code_id={cs.code_id}  first_seen={cs.first_seen_ts:.0f}  hash={cs.data_hash[:12]}...")
    print(f"  New contracts ({nd.new_contracts_count}):")
    for e in nd.new_contracts:
        print(f"    block={e.block_height}  {e.address}  label={e.label!r}")

    return wasm_cache


async def dbg_wasm_period_stats(app: LpAppFramework, wasm_cache: WasmCache = None):
    """Build WasmPeriodStats using WasmStatsBuilder and print a full report."""
    if wasm_cache is None:
        wasm_cache = WasmCache(app.deps.thor_connector, db=app.deps.db)

    recorder = CosmWasmRecorder(app.deps.db)
    builder = WasmStatsBuilder(
        wasm_cache=wasm_cache,
        recorder=recorder,
        last_block_cache=app.deps.last_block_cache,
        contract_name_cache=app.deps.rujira_contract_name_cache,
        top_label_limit=app.deps.cfg.as_int('rujira.contract_names.infographic_name_limit', 32),
    )

    sep()
    print(">>> Building WasmPeriodStats (last 7 days)...")
    t0 = time.perf_counter()
    ps = await builder.build(days=7, top_n=10)
    elapsed = time.perf_counter() - t0

    sep()
    print(f"Built in {elapsed:.2f}s")
    print(f"Period : {datetime.fromtimestamp(ps.period_start_ts)} — "
          f"{datetime.fromtimestamp(ps.period_end_ts)}")
    print()
    print(f"Codes     : {ps.total_codes:>6}  (+{ps.new_codes} new)")
    print(f"Contracts : {ps.total_contracts:>6}  (+{ps.new_contracts} new)")
    print()
    pct_calls = f"{ps.calls_change_pct:+.1f}%" if ps.calls_change_pct is not None else "n/a"
    pct_users = f"{ps.users_change_pct:+.1f}%" if ps.users_change_pct is not None else "n/a"
    print(f"Calls (cur / prev) : {ps.total_calls:>8} / {ps.prev_total_calls:>8}  {pct_calls}")
    print(f"Users (cur / prev) : {ps.unique_users:>8} / {ps.prev_unique_users:>8}  {pct_users}")

    sep()
    print(f"Top contracts ({len(ps.top_contracts)}):")
    for i, tc in enumerate(ps.top_contracts, 1):
        print(f"  {i:>2}. calls={tc.calls:>6}  users={tc.unique_users:>5}"
              f"  label={tc.label!r}  display={tc.display_label!r}")
        print(f"      {tc.address}")

    sep()
    print(f"Daily chart ({len(ps.daily_chart)} day(s)):")
    for pt in ps.daily_chart:
        day = datetime.fromtimestamp(pt.ts).strftime("%Y-%m-%d")
        bar = "#" * min(40, pt.calls // max(1, ps.total_calls // 40))
        print(f"  {day}  calls={pt.calls:>6}  users={pt.unique_users:>5}  {bar}")


class WasmRecordProgressPrinter(INotified):
    """Prints a one-line summary after every *print_every* blocks."""

    def __init__(self, recorder: CosmWasmRecorder, print_every: int = 100):
        self.recorder = recorder
        self.print_every = print_every
        self._count = 0

    async def on_data(self, sender, block: BlockResult):
        self._count += 1
        if self._count % self.print_every == 0:
            block_ts = float(block.timestamp) if block.timestamp else now_ts()
            calls_today = await self.recorder.get_daily_calls(block_ts)
            users_today = await self.recorder.get_daily_unique_users(block_ts)
            calls_7d = await self.recorder.get_calls_range(block_ts - 7 * DAY, block_ts)
            total_7d = sum(int(float(d.get(CosmWasmRecorder.KEY_CALLS, 0))) for d in calls_7d.values())
            print(
                f"  block #{block.block_no:>9}  "
                f"calls today={calls_today:>6}  users today={users_today:>5}  "
                f"calls 7d={total_7d:>7}  "
                f"({datetime.now().strftime('%H:%M:%S')})"
            )


async def dbg_continuous_record(app: LpAppFramework, blocks_back: int = 10000, start_block: int | None = None):
    """
    Replay historical blocks (using BlockScannerCached for caching)
    and record every CosmWasm MsgExecuteContract into CosmWasmRecorder.

    By default, replays the last *blocks_back* blocks. If *start_block* is
    provided, it takes precedence and scanning begins from that explicit block.
    Stops automatically when it reaches the current tip block.
    """
    d = app.deps
    current_block = await d.last_block_cache.get_thor_block()

    if start_block is None:
        if blocks_back <= 0:
            raise ValueError(f'blocks_back must be positive, got {blocks_back!r}')
        start_block = current_block - blocks_back
        start_desc = f'{blocks_back:,} blocks back'
    else:
        start_block = int(start_block)
        if start_block < 0:
            raise ValueError(f'start_block must be non-negative, got {start_block!r}')
        if start_block >= current_block:
            raise ValueError(
                f'start_block must be below current block {current_block:,}, got {start_block:,}'
            )
        blocks_back = current_block - start_block
        start_desc = 'explicit start block'

    sep()
    print(f">>> Continuous WASM recorder")
    print(f"    current block : {current_block:,}")
    print(f"    start block   : {start_block:,}  ({start_desc})")
    print(f"    stop block    : {current_block:,}")
    print(f"    stride        : 20")
    print(f"    ~blocks to scan: {blocks_back // 20:,}")
    print()

    d.block_scanner = BlockScannerCached(d, last_block=start_block, stride=20, stop_block=current_block)

    recorder = CosmWasmRecorder(d.db)
    d.block_scanner.add_subscriber(recorder)

    printer = WasmRecordProgressPrinter(recorder, print_every=100)
    d.block_scanner.add_subscriber(printer)

    try:
        await d.block_scanner.run()
    except asyncio.CancelledError:
        pass

    sep()
    print(">>> Recording done.")


async def dbg_save_demo_json(app: LpAppFramework, days: float = 7.0, top_n: int = 10):
    """
    Build a real WasmPeriodStats from live Redis data and write it to the renderer
    demo file so the front-end developer can iterate on the template.
    """
    wasm_cache = WasmCache(app.deps.thor_connector, db=app.deps.db)
    recorder = CosmWasmRecorder(app.deps.db)
    builder = WasmStatsBuilder(
        wasm_cache=wasm_cache,
        recorder=recorder,
        last_block_cache=app.deps.last_block_cache,
        contract_name_cache=app.deps.rujira_contract_name_cache,
        top_label_limit=app.deps.cfg.as_int('rujira.contract_names.infographic_name_limit', 32),
    )

    sep()
    print(f">>> Building WasmPeriodStats ({days}d, top {top_n}) for demo JSON...")
    t0 = time.perf_counter()
    ps = await builder.build(days=days, top_n=top_n)
    elapsed = time.perf_counter() - t0
    print(f"    Built in {elapsed:.2f}s  |  {ps}")

    payload = {
        "template_name": "app_layer_stats.jinja2",
        "parameters": ps.to_dict(),
    }

    with open(DEMO_JSON_PATH, 'w') as f:
        json.dump(payload, f, indent=2)

    sep()
    print(f"Saved to {DEMO_JSON_PATH}")
    print(f"  codes={ps.total_codes}  contracts={ps.total_contracts}")
    print(f"  calls={ps.total_calls} ({ps.calls_change_pct:+.1f}%)" if ps.calls_change_pct is not None
          else f"  calls={ps.total_calls} (no prev data)")
    print(f"  users={ps.unique_users} ({ps.users_change_pct:+.1f}%)" if ps.users_change_pct is not None
          else f"  users={ps.unique_users} (no prev data)")
    print(f"  top contracts: {len(ps.top_contracts)}, chart points: {len(ps.daily_chart)}")


async def dbg_broadcast_app_layer_stats(app: LpAppFramework):
    """
    Trigger the public app-layer job through PublicScheduler registration,
    so the debug path matches the scheduler-executed production path.
    """
    sep()
    print(f">>> Running public job via scheduler: {PubAlertJobNames.APP_LAYER_STATS!r}...")
    t0 = time.perf_counter()
    result = await app.deps.pub_scheduler.run_job_by_function(PubAlertJobNames.APP_LAYER_STATS)
    elapsed = time.perf_counter() - t0

    sep()
    print(f"Scheduler result: {result}")
    print(f"Elapsed: {elapsed:.2f}s")
    return result


async def main():
    app = LpAppFramework(log_level=logging.INFO)
    async with app:
        # comment/uncomment the desired debug function(s) below:

        await dbg_broadcast_app_layer_stats(app)
        # await dbg_save_demo_json(app)
        # await dbg_continuous_record(app, start_block=24_812_774)
        # await dbg_continuous_record(app, blocks_back=20_000)


if __name__ == '__main__':
    asyncio.run(main())
