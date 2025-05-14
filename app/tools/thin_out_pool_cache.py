import asyncio
import logging

from jobs.fetch.pool_price import PoolFetcher
from tools.lib.lp_common import LpAppFramework


async def thin_out_pool_cache(app):
    pf: PoolFetcher = app.deps.pool_fetcher

    scan_batch_size = int(input("Enter scan batch size (default 1000): ") or 1000)
    min_distance = int(input("Enter minimum distance (default 5): ") or 5)
    max_keys_to_delete = int(input("Enter maximum keys to delete (default 10000): ") or 10000)

    keys = await pf.cache.get_thin_out_keys(
        min_distance=min_distance,
        scan_batch_size=scan_batch_size,
        max_keys_to_delete=max_keys_to_delete,
    )
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
