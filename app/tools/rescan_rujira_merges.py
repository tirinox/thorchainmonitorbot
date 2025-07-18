import asyncio

from jobs.ruji_merge import RujiMergeTracker
from jobs.scanner.block_result import BlockResult
from jobs.scanner.native_scan import BlockScanner
from lib.constants import THOR_BLOCK_TIME
from lib.date_utils import DAY, HOUR
from lib.delegates import INotified
from lib.logs import WithLogger
from models.ruji import EventRujiMerge
from tools.lib.lp_common import LpAppFramework

# INTERVAL = 3 * HOUR / THOR_BLOCK_TIME
INTERVAL = 7 * DAY / THOR_BLOCK_TIME


class ReceiveRujiraMerge(INotified, WithLogger):
    def __init__(self, app: LpAppFramework, start, end):
        super().__init__()
        self.app = app
        self.total_found = 0
        self.start = start
        self.end = end

    async def on_data(self, sender, data):
        if isinstance(data, EventRujiMerge):
            print(f"Found merge: {data.tx_id} {data.asset} {data.amount} {data.from_address} {data.volume_usd:.2f} USD")
            self.total_found += 1
            print(f"Total found so far: {self.total_found}")
        elif isinstance(data, BlockResult):
            self.show_progress(data.block_no)

    def show_progress(self, height):
        progress = (height - self.start) / (self.end - self.start) * 100.0
        print(f"Block height: {height}, blocks from starts {height - self.start}, progress {progress:.2f}%")


async def rescan_rujira_merges(app: LpAppFramework):
    d = app.deps
    d.block_scanner.initial_sleep = 0

    await d.pool_fetcher.run_once()
    d.last_block_fetcher.add_subscriber(d.last_block_store)
    await d.last_block_fetcher.run_once()

    force_start_block = d.last_block_store.thor - int(INTERVAL)
    recv = ReceiveRujiraMerge(app, start=force_start_block, end=d.last_block_store.thor)

    ruji_merge_tracker = RujiMergeTracker(d)
    d.block_scanner.add_subscriber(ruji_merge_tracker)
    d.block_scanner.add_subscriber(recv)

    ruji_merge_tracker.add_subscriber(recv)

    d.block_scanner.last_block = force_start_block
    await d.block_scanner.run()


async def run():
    app = LpAppFramework()
    async with app(brief=True):
        await rescan_rujira_merges(app)


if __name__ == '__main__':
    asyncio.run(run())
