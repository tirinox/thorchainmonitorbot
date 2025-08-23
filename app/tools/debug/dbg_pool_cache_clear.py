import asyncio
import json
import logging

from jobs.fetch.pool_price import PoolFetcher
from lib.date_utils import DAY
from tools.lib.lp_common import LpAppFramework

TEMP_POOL_CACHE_FILE = '../temp/pool_cache.json'


async def save_all_pool_data(app: LpAppFramework):
    # if exists, ask a confirmation
    with open(TEMP_POOL_CACHE_FILE, 'r') as f:
        pool_cache = json.load(f)
        print(f'Loaded {len(pool_cache)} pool data from {TEMP_POOL_CACHE_FILE}')
        if input('Do you want to overwrite it? (y/n) ').lower() != 'y':
            print('Cancelled')
            return

    r = await app.deps.db.get_redis()
    pool_cache = await r.hgetall(PoolFetcher.DB_KEY_POOL_INFO_HASH)
    with open(TEMP_POOL_CACHE_FILE, 'w') as f:
        json.dump(pool_cache, f, indent=2)
    print(f'Saved {len(pool_cache)} pool data to {TEMP_POOL_CACHE_FILE}')


async def upload_all_pool_data(app: LpAppFramework):
    # check if the file exists
    try:
        with open(TEMP_POOL_CACHE_FILE, 'r') as f:
            pool_cache = json.load(f)
    except FileNotFoundError:
        print(f'File {TEMP_POOL_CACHE_FILE} not found')
        return

    r = await app.deps.db.get_redis()
    await r.delete(PoolFetcher.DB_KEY_POOL_INFO_HASH)

    async with r.pipeline() as pipe:
        for k, v in pool_cache.items():
            await pipe.hset(PoolFetcher.DB_KEY_POOL_INFO_HASH, k, v)
        await pipe.execute()

    print(f'Uploaded {len(pool_cache)} pool data to redis')


async def simulate_pool_cache_clear(app: LpAppFramework):
    pf: PoolFetcher = app.deps.pool_fetcher
    pf._pool_cache_clear_every = 3
    pf.pool_cache_max_age = 7 * DAY

    await upload_all_pool_data(app)

    iterations = 1
    while True:
        print(f'Iteration #{iterations}')
        await pf.run_once()
        await asyncio.sleep(1)
        iterations += 1


async def do_job(app: LpAppFramework):
    # await save_all_pool_data(app)
    # await upload_all_pool_data(app)
    await simulate_pool_cache_clear(app)


async def main():
    app = LpAppFramework(log_level=logging.INFO)
    async with app(brief=True):
        await do_job(app)


if __name__ == "__main__":
    asyncio.run(main())
