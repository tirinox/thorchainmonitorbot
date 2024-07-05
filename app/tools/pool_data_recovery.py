"""
This script helps you to restore the historical pool data from the database backup.
You need to run redis-server somewhere and provide the connection details.

The pool data from the removed pool_info table will be restored to the local redis database.
Target redis database connection details should be provided in the .env file.

Usage:

    make attach
    PYTHONPATH="/app" python tools/pool_data_recovery.py --host localhost --port 6379 --password secret --db 0
"""
import argparse
import asyncio
import json
import pprint

import tqdm
from redis.asyncio import Redis

from services.jobs.fetch.pool_price import PoolFetcher
from services.lib.db import DB


async def get_remote_redis() -> Redis:
    # parse command line arguments
    parser = argparse.ArgumentParser(description='Pool data recovery script')
    parser.add_argument('--host', type=str, help='Redis host', required=True)
    parser.add_argument('--port', type=int, help='Redis port', default=6379)
    parser.add_argument('--password', type=str, help='Redis password', default=None)
    parser.add_argument('--db', type=int, help='Redis database number', default=0)
    args = parser.parse_args()

    # connect to the remote redis
    redis = Redis(host=args.host, port=args.port, db=args.db, password=args.password)
    await ping_redis(redis)
    return redis


async def ping_redis(redis: Redis):
    ping = await redis.ping()
    print(f'Ping of {redis} is {ping}')
    if not ping:
        raise Exception('Redis is not available')


async def get_target_redis() -> Redis:
    # connect to the target redis
    loop = asyncio.get_event_loop()
    db = DB(loop)
    redis = await db.get_redis()

    await ping_redis(redis)
    return redis


POOL_DATA_KEY_V2 = PoolFetcher.DB_KEY_POOL_INFO_HASH
POOL_DATA_KEY_V1 = 'PoolInfo:hashtable'  # ignore


async def get_number_of_keys(redis: Redis, key: str) -> int:
    return await redis.hlen(key)


async def print_sample(redis: Redis, key: str):
    # get the first key of the hashtable
    all_keys = await redis.hkeys(key)
    if not all_keys:
        print('No keys found')
    else:
        first_key = all_keys[0]
        value = await redis.hget(key, first_key)
        try:
            j = json.loads(value)
        except:
            print(f'Value of {key} is not a valid JSON')
            j = value
        print(f'Sample of {key} / {first_key}')
        print(f'First key: {first_key}')
        pprint.pprint(j)


async def analise_intersection(r1, r2, key):
    print(f'Loading keys for {key} @ {r1}')
    all_keys_r1 = await r1.hkeys(key)
    print(f'Loading keys for {key} @ {r1}')
    all_keys_r2 = await r2.hkeys(key)

    common_keys = set(all_keys_r1) & set(all_keys_r2)
    print(f'Total common keys: {len(common_keys)}')


BATCH_SIZE = 100  # Adjust batch size as needed
CONCURRENCY_LIMIT = 10  # Adjust concurrency limit as needed


async def transfer_key(key, source_redis, target_redis, table_name):
    if not await target_redis.hget(table_name, key):
        value = await source_redis.hget(table_name, key)
        await target_redis.hset(table_name, key, value)


async def transfer_batch(keys_batch, source_redis, target_redis, table_name):
    async with asyncio.Semaphore(CONCURRENCY_LIMIT):
        tasks = []
        for key in keys_batch:
            tasks.append(transfer_key(key, source_redis, target_redis, table_name))
        await asyncio.gather(*tasks)


async def restore_backup(source_redis: Redis, target_redis: Redis, table_name):
    print(f'Loading keys {table_name} from {source_redis}')
    all_keys_r1 = await source_redis.hkeys(table_name)

    for i in tqdm.tqdm(range(0, len(all_keys_r1), BATCH_SIZE)):
        keys_batch = all_keys_r1[i:i + BATCH_SIZE]
        await transfer_batch(keys_batch, source_redis, target_redis, table_name)


async def main():
    remote_redis = await get_remote_redis()
    target_redis = await get_target_redis()

    # get the number of keys in the remote redis
    number_of_keys = await get_number_of_keys(remote_redis, POOL_DATA_KEY_V2)
    print(f'Number of keys {POOL_DATA_KEY_V2} in the remote redis: {number_of_keys}')

    number_of_keys = await get_number_of_keys(remote_redis, POOL_DATA_KEY_V1)
    print(f'Number of keys {POOL_DATA_KEY_V1} in the remote redis: {number_of_keys}')

    # sep()
    # await print_sample(target_redis, POOL_DATA_KEY_V2)
    # sep()

    # await analise_intersection(remote_redis, target_redis, POOL_DATA_KEY_V2)

    await restore_backup(remote_redis, target_redis, POOL_DATA_KEY_V2)

    await remote_redis.aclose()
    await target_redis.aclose()


if __name__ == '__main__':
    asyncio.run(main())
