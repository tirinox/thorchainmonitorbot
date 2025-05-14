import asyncio
import logging

import tqdm

from jobs.fetch.pool_price import PoolFetcher
from lib.utils import grouper
from tools.lib.lp_common import LpAppFramework


async def thin_out_pool_cache(app):
    pf: PoolFetcher = app.deps.pool_fetcher
    keys = await pf.cache.get_thin_out_keys(min_distance=5, scan_batch_size=1000)
    print(f"Total keys to delete: {len(keys)}")

    # await pf.cache.backup_hash()

    # Ask if the user wants to delete the keys
    confirm = input(f"Do you want to delete {len(keys)} keys? (y/n): ")
    if confirm.lower().strip() == 'y':
        # Delete the keys in batches
        await pf.cache.delete_keys_batched(keys)
        print(f"Deleted {len(keys)} keys.")
    else:
        print("No keys deleted.")


async def main():
    app = LpAppFramework(log_level=logging.DEBUG)
    async with app(brief=True):
        await thin_out_pool_cache(app)


if __name__ == '__main__':
    asyncio.run(main())
