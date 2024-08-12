"""
    Copy subtree from one redis to another
"""
import sys

import redis
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), 'redis_copy_keys.env'))


def analise_keys(src_redis, pattern):
    cursor = 0
    n = 0
    i = 1
    while True:
        cursor, keys = src_redis.scan(cursor=cursor, match=pattern, count=1000)
        if not keys:
            break

        if i < 100:
            for key in keys:
                print(f'{i: 6}: {key}')
                i += 1

        n += len(keys)

        if cursor == 0:
            break

    print(f'Total keys to copy: {n}')


def copy_keys(src_redis, dst_redis, pattern):
    """
    Copies all keys matching the given pattern from the source Redis instance to the destination Redis instance.

    :param src_redis: Source Redis connection object
    :param dst_redis: Destination Redis connection object
    :param pattern: Key pattern to match keys to copy
    """
    cursor = 0
    while True:
        cursor, keys = src_redis.scan(cursor=cursor, match=pattern, count=1000)
        if not keys:
            break

        for key in keys:
            value = src_redis.dump(key)
            ttl = src_redis.ttl(key)
            if value is not None:
                dst_redis.restore(key, ttl if ttl > 0 else 0, value, replace=True)

        if cursor == 0:
            break


def main():
    # Get source Redis credentials from environment variables
    src_redis = redis.StrictRedis(
        host=(host_scr := os.getenv('SRC_REDIS_HOST')),
        port=(port_scr := int(os.getenv('SRC_REDIS_PORT'))),
        db=(db_src := int(os.getenv('SRC_REDIS_DB'))),
        password=os.getenv('SRC_REDIS_PASSWORD'),
        decode_responses=True
    )
    print(src_redis.ping())

    # Get destination Redis credentials from environment variables
    dst_redis = redis.StrictRedis(
        host=(host_dst := os.getenv('DST_REDIS_HOST')),
        port=(port_dst := int(os.getenv('DST_REDIS_PORT'))),
        db=(db_dst := int(os.getenv('DST_REDIS_DB'))),
        password=os.getenv('DST_REDIS_PASSWORD'),
        decode_responses=True
    )
    print(dst_redis.ping())

    print(f'From {host_scr}:{port_scr}:{db_src} => '
          f'{host_dst}:{port_dst}:{db_dst}')

    # Pattern to match keys
    key_pattern = sys.argv[1] if len(sys.argv) == 2 else input('Enter key pattern:')

    analise_keys(src_redis, key_pattern)

    # sure?
    if input('Are you sure? Y/N?').upper().strip() != 'Y':
        print('abort!')
        return

    # Copy keys from source to destination
    copy_keys(src_redis, dst_redis, key_pattern)
    print(f"Keys matching pattern '{key_pattern}' have been copied from source to destination Redis.")


if __name__ == "__main__":
    main()
