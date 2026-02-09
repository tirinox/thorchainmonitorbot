import argparse
import asyncio
import logging

from jobs.vote_recorder import VoteRecorder
from lib.date_utils import DAY, HOUR, now_ts, parse_timespan_to_seconds
from lib.utils import parallel_run_in_groups
from tools.lib.lp_common import LpAppFramework


async def rescan_vote_history(app: LpAppFramework,
                              start_ago_sec=30 * DAY,
                              interval_sec=2 * HOUR,
                              overwrite=False):
    d = app.deps

    vote_recorder = VoteRecorder(d)
    vote_recorder.overwrite = overwrite
    app.deps.mimir_cache.step_sleep = 0.01

    now = int(now_ts())

    async def process_one_timestamp(ts):
        if await vote_recorder.get_point(ts):
            if not overwrite:
                app.logger.info(f"Already have data for timestamp {ts}, skipping")
                return
            else:
                app.logger.info(f"Already have data for timestamp {ts}, but overwrite is True, processing anyway")

        block = await vote_recorder.block_mapper.bl
        mimir_tuple = await app.deps.mimir_cache.get(height=block, forced=True)
        mimir_tuple.ts = ts
        await vote_recorder.on_data(sender=None, data=mimir_tuple)

    tasks = [process_one_timestamp(ts) for ts in range(
        int(now - start_ago_sec),
        int(now),
        int(interval_sec)
    )]
    await parallel_run_in_groups(tasks, 10, use_tqdm=True)


def arg_parser():
    parser = argparse.ArgumentParser(description='Rescan voting history')
    parser.add_argument('--start-ago', type=str, default='30d', help='How far back to start rescanning (30d)')
    parser.add_argument('--interval', type=str, default='2h', help='Interval between data points (2h)')
    parser.add_argument('--overwrite', action='store_true', help='Whether to overwrite existing data')
    return parser.parse_args()


async def main():
    app = LpAppFramework(log_level=logging.INFO)
    async with app:
        args = arg_parser()
        start_ago_sec = parse_timespan_to_seconds(args.start_ago)
        interval_sec = parse_timespan_to_seconds(args.interval)
        await rescan_vote_history(app, start_ago_sec=start_ago_sec, interval_sec=interval_sec, overwrite=args.overwrite)


if __name__ == '__main__':
    asyncio.run(main())
