import asyncio
import logging

from jobs.fetch.pool_price import PoolFetcher
from tools.lib.lp_common import LpAppFramework


async def load_historic_data_task(app):
    pf: PoolFetcher = app.deps.pool_fetcher

    block_distance = int(input("Enter distance in blocks (default 10): ") or 5)
    max_blocks = int(input("Enter maximum blocks to scan (default 1000): ") or 1000)

    print(f"Loading {max_blocks} blocks with a distance of {block_distance}.")
    await pf.load_historic_data(max_blocks, block_distance, use_tqdm=True)


async def main():
    app = LpAppFramework(log_level=logging.DEBUG)
    async with app(brief=True):
        await load_historic_data_task(app)


if __name__ == '__main__':
    asyncio.run(main())
