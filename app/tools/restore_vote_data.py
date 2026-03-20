import asyncio
import logging
from typing import List

from jobs.runeyield.date2block import DateToBlockMapper
from jobs.vote_recorder import VoteRecorder
from lib.constants import THOR_BLOCK_TIME
from lib.date_utils import DAY
from lib.utils import parallel_run_in_groups
from models.mimir import MimirHolder
from models.mimir_naming import MIMIR_DICT_FILENAME
from models.node_info import NetworkNodes, NodeInfo
from tools.lib.lp_common import LpAppFramework


async def restore_vote_records_from_past(app: LpAppFramework, days: int = 30, interval: int = 1000,
                                         concurrency: int = 10):
    d = app.deps

    vote_recorder = VoteRecorder(d)
    app.deps.mimir_cache.step_sleep = 0.01

    last_block = await app.deps.last_block_cache.get_thor_block()
    past_block = last_block - int(days * DAY / THOR_BLOCK_TIME)

    holder = MimirHolder()
    holder.mimir_rules.load(MIMIR_DICT_FILENAME)


    block_mapper = DateToBlockMapper(app.deps)

    async def process_one_block(block):
        try:
            mimir_tuple = await app.deps.mimir_cache.get_for_height_no_cache(block, only_votes=True)
            block_date = await block_mapper.get_datetime_by_block_height(block)
            mimir_tuple.ts = block_date.timestamp() if block_date else 0

            node_list: List[NodeInfo] = await app.deps.node_cache.fetch_node_list(height=block)
            nodes = NetworkNodes(node_list, {})

            holder.update_voting(mimir_tuple, nodes.active_nodes)
            holder.last_timestamp = mimir_tuple.ts
            holder.last_thor_block = block
            await vote_recorder.on_data(sender=None, data=holder)
        except Exception as e:
            print(f'[Error] Failed to process block {block}: {e}')

    tasks = [process_one_block(block) for block in reversed(range(past_block, last_block, interval))]
    await parallel_run_in_groups(tasks, concurrency, use_tqdm=True)


async def main():
    days = int(input('How many days to restore [30]: ').strip() or 30)
    interval = int(input('Interval in blocks [1200]: ').strip() or 1200)
    concurrency = int(input('Concurrency [10]: ').strip() or 10)
    clear_first = (input('Clear existing vote data before restoring? [y/N]: ').strip().lower() == 'y')

    app = LpAppFramework(log_level=logging.DEBUG)
    async with app:
        if clear_first:
            vote_recorder = VoteRecorder(app.deps)
            n = await vote_recorder.clear_all()
            print(f'Cleared {n} Redis keys.')
        await restore_vote_records_from_past(app, days=days, interval=interval, concurrency=concurrency)


if __name__ == '__main__':
    asyncio.run(main())
