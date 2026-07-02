"""
Usage:
    make attach
    PYTHONPATH="/app" python tools/migrate_pool_cache_redis_to_keydb.py /config/config.yaml
"""
import asyncio
import logging

from jobs.fetch.cached.pool import PoolCache
from tools.lib.lp_common import LpAppFramework, ask_yes_no

DEFAULT_SCAN_BATCH_SIZE = 1000


async def migrate_pool_cache(app: LpAppFramework):
    redis = await app.deps.db.get_redis()
    keydb = await app.deps.keydb.get_redis()
    hash_name = PoolCache.DB_KEY_POOL_INFO_HASH

    source_count = await redis.hlen(hash_name)
    target_count_before = await keydb.hlen(hash_name)

    print(f'Source Redis key: {hash_name}')
    print(f'Source Redis entries: {source_count}')
    print(f'Target KeyDB entries before migration: {target_count_before}')

    if source_count == 0:
        print('Source pool cache empty. Nothing to migrate.')
        return

    if target_count_before > 0 and not ask_yes_no(
        f'Target KeyDB already has {target_count_before} entries. Merge into existing hash?',
        default=False,
    ):
        print('Cancelled.')
        return

    scan_batch_size = int(input(f'Enter scan batch size (default {DEFAULT_SCAN_BATCH_SIZE}): ') or DEFAULT_SCAN_BATCH_SIZE)

    migrated = 0
    cursor = 0
    while True:
        cursor, data = await redis.hscan(name=hash_name, cursor=cursor, count=scan_batch_size)
        if data:
            await keydb.hset(hash_name, mapping=data)
            migrated += len(data)
            print(f'Migrated {migrated}/{source_count} entries...')
        if cursor == 0:
            break

    target_count_after = await keydb.hlen(hash_name)
    print(f'Migration done. Source Redis entries: {source_count}. Target KeyDB entries now: {target_count_after}.')

    if target_count_after < source_count:
        print('Target KeyDB has fewer entries than source Redis. Refuse source flush.')
        return

    if ask_yes_no(f'Flush old Redis pool cache key "{hash_name}"?', default=False):
        await redis.delete(hash_name)
        print(f'Deleted source Redis key: {hash_name}')
    else:
        print('Source Redis key kept.')


async def main():
    app = LpAppFramework(log_level=logging.INFO)
    async with app:
        await migrate_pool_cache(app)


if __name__ == '__main__':
    asyncio.run(main())

