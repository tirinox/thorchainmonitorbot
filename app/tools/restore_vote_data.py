import argparse
import asyncio
import logging

from jobs.runeyield.date2block import DateToBlockMapper
from jobs.vote_recorder import VoteRecorder
from lib.constants import THOR_BLOCK_TIME
from lib.date_utils import DAY
from lib.utils import parallel_run_in_groups
from models.mimir import MimirHolder
from models.mimir_naming import MIMIR_DICT_FILENAME
from models.node_info import NetworkNodes
from tools.lib.lp_common import LpAppFramework


async def restore_vote_records_from_past(app: LpAppFramework, days: int = 30, interval: int = 100,
                                         concurrency: int = 10):
    d = app.deps

    vote_recorder = VoteRecorder(d)
    app.deps.mimir_cache.step_sleep = 0.01

    last_block = await app.deps.last_block_cache.get_thor_block()
    past_block = last_block - int(days * DAY / THOR_BLOCK_TIME)

    holder = MimirHolder()
    holder.mimir_rules.load(MIMIR_DICT_FILENAME)

    # let's pretend that active nodes haven't changed for the past blocks
    nodes: NetworkNodes = await app.deps.node_cache.get()

    block_mapper = DateToBlockMapper(app.deps)

    async def process_one_block(block):
        try:
            mimir_tuple = await app.deps.mimir_cache.get_for_height_no_cache(block, only_votes=True)
            block_date = await block_mapper.get_datetime_by_block_height(block)
            mimir_tuple.ts = block_date.timestamp() if block_date else 0
            holder.update_voting(mimir_tuple, nodes.active_nodes)
            holder.last_timestamp = mimir_tuple.ts
            holder.last_thor_block = block
            await vote_recorder.on_data(sender=None, data=holder)
        except Exception as e:
            print(f'[Error] Failed to process block {block}: {e}')

    tasks = [process_one_block(block) for block in reversed(range(past_block, last_block, interval))]
    await parallel_run_in_groups(tasks, concurrency, use_tqdm=True)


async def main():
    parser = argparse.ArgumentParser(description='Restore vote records from past blocks.')
    parser.add_argument('--days', type=int, default=30, help='How many days to restore (default: 30)')
    parser.add_argument('--interval', type=int, default=100, help='Interval in blocks (default: 100)')
    parser.add_argument('--concurency', type=int, default=10, help='Concurrency level (default: 10)')
    args = parser.parse_args()

    app = LpAppFramework(log_level=logging.DEBUG)
    async with app:
        await restore_vote_records_from_past(app, days=args.days, interval=args.interval,
                                             concurrency=args.concurency)


if __name__ == '__main__':
    asyncio.run(main())
