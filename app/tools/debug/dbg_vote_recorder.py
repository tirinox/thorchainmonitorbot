import asyncio
import logging
import random
import time
from datetime import datetime

from jobs.fetch.mimir import ConstMimirFetcher
from jobs.runeyield.date2block import DateToBlockMapper
from jobs.vote_recorder import VoteRecorder
from lib.constants import THOR_BLOCK_TIME
from lib.date_utils import DAY
from lib.texts import sep
from lib.utils import parallel_run_in_groups
from tools.lib.lp_common import LpAppFramework


async def dbg_vote_recorder_continuous(app: LpAppFramework):
    d = app.deps
    mimir_fetcher = ConstMimirFetcher(d)

    vote_recorder = VoteRecorder(d)
    mimir_fetcher.add_subscriber(vote_recorder)

    await mimir_fetcher.run()


async def dbg_vote_record_from_past(app: LpAppFramework, overwrite=False):
    d = app.deps
    # mimir_fetcher = ConstMimirFetcher(d)

    vote_recorder = VoteRecorder(d)
    app.deps.mimir_cache.step_sleep = 0.01

    last_block = await app.deps.last_block_cache.get_thor_block()
    past_block = last_block - int(120 * DAY / THOR_BLOCK_TIME)
    # interval = (last_block - past_block) // 10
    interval = 1000

    async def process_one_block(block):
        mimir_tuple = await app.deps.mimir_cache.get(height=block, forced=True)
        await vote_recorder.on_data(sender=None, data=mimir_tuple)

    tasks = [process_one_block(block) for block in range(past_block, last_block, interval)]
    await parallel_run_in_groups(tasks, 10, use_tqdm=True)


async def dbg_time_discovery_single(app: LpAppFramework, block: int):
    dbm = DateToBlockMapper(app.deps)
    t0 = time.monotonic()
    dt = await dbm.get_datetime_by_block_height(block)
    t1 = time.monotonic()

    real_ts = await dbm.get_timestamp_by_block_height_precise(block)
    off_time = abs(real_ts - dt.timestamp())

    print(f"Block {block} -> {dt} (took {t1 - t0:.2f} seconds), off by {off_time:.2f} seconds)")

    return {
        "block": block,
        "datetime": dt,
        "time_taken": t1 - t0,
        "off_time": off_time,
        "real_ts": real_ts,
        "estimated_ts": dt.timestamp(),
        "real_dt": datetime.fromtimestamp(real_ts),
        "estimated_dt": dt,
    }


async def dbg_time_discovery_benchmark(app: LpAppFramework, n_tests=100):
    last_thor_block = await app.deps.last_block_cache.get_thor_block()
    past_thor_block = last_thor_block - 1_000_000
    for i in range(n_tests):
        block = random.randint(past_thor_block, last_thor_block)
        await dbg_time_discovery_single(app, block)


async def dbg_mimir_at_block(app: LpAppFramework):
    last_block = await app.deps.last_block_cache.get_thor_block()
    print('last_block', last_block)
    past_block = last_block - 1000
    mimir_tuple = await app.deps.mimir_cache.get(height=past_block)
    print('mimir_tuple', mimir_tuple)

    sep()
    dbm = DateToBlockMapper(app.deps)
    block_ts = await dbm.get_timestamp_by_block_height_precise(past_block)
    print('block_ts', block_ts, datetime.fromtimestamp(block_ts))


async def main():
    app = LpAppFramework(log_level=logging.INFO)
    async with app:
        # await dbg_mimir_at_block(app)
        # await dbg_time_discovery_single(app, 24703873)
        # await dbg_time_discovery_benchmark(app, 300)
        await dbg_vote_record_from_past(app)


if __name__ == '__main__':
    asyncio.run(main())
