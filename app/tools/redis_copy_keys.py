"""
    Copy subtree from one redis to another
"""
import os
import sys

import tqdm
from dotenv import load_dotenv

from tools.lib.remote_redis import get_redis

# Load environment variables from .env file
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), 'redis_copy_keys.env'))


def analise_keys(src_redis, pattern):
    keys = src_redis.keys(pattern)
    print(f'Total keys to copy: {len(keys)}')
    return keys


def copy_keys(src_redis, dst_redis, pattern):
    """
    Copies all keys matching the given pattern from the source Redis instance to the destination Redis instance.

    :param src_redis: Source Redis connection object
    :param dst_redis: Destination Redis connection object
    :param pattern: Key pattern to match keys to copy
    """
    keys = src_redis.keys(pattern)
    prints = len(keys) < 100
    for key in tqdm.tqdm(keys):
        value = src_redis.dump(key)
        ttl = src_redis.ttl(key)
        if value is not None:
            dst_redis.restore(key, ttl if ttl > 0 else 0, value, replace=True)

        if prints:
            print(f'Copied key: {key}')


def main():
    # Get source Redis credentials from environment variables
    if not (src_redis := get_redis('SRC')):
        return

    # Get destination Redis credentials from environment variables
    if not (dst_redis := get_redis('DST')):
        return

    # Pattern to match keys
    key_pattern = sys.argv[1] if len(sys.argv) == 2 else input('Enter key pattern:')
    key_pattern = key_pattern.strip()
    if not key_pattern:
        print('Invalid key pattern.')
        return

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
