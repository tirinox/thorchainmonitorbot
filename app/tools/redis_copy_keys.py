"""
    Copy subtree from one redis to another

    Examples:

    1. Copy volume data:
    Pattern: Accum:Volume:*
    Filter: int(key.split(":")[-1]) > 1741248997 - 60 * 60 * 24 * 7
     or
    #: python redis_copy_keys.py --pattern "Accum:Volume:*" --filter "int(key.split(':')[-1]) > ts - 60 * 60 * 24 * 7"

    2. Copy price data
    Pattern: ts-stream:price*
    Filter: None

    Redis credentials are loaded from "redis_copy_keys.env" file in the same directory as this script.
"""
import datetime
import os
import sys
from pprint import pprint

import tqdm
from dotenv import load_dotenv

from tools.lib.remote_redis import get_redis

# Load environment variables from .env file
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), 'redis_copy_keys.env'))


def analise_keys(src_redis, pattern):
    keys = src_redis.keys(pattern)
    print(f'Total keys found before filters: {len(keys)}')
    return keys


def copy_keys(src_redis, dst_redis, keys):
    """
    Copies all keys matching the given pattern from the source Redis instance to the destination Redis instance.

    :param src_redis: Source Redis connection object
    :param dst_redis: Destination Redis connection object
    :param pattern: Key pattern to match keys to copy
    """
    prints = len(keys) < 100
    for key in tqdm.tqdm(keys):
        value = src_redis.dump(key)
        ttl = src_redis.ttl(key)
        if value is not None:
            dst_redis.restore(key, ttl if ttl > 0 else 0, value, replace=True)

        if prints:
            print(f'Copied key: {key}')


def filter_keys(keys, filter_text):
    # current timestamp
    ts = datetime.datetime.now().timestamp()

    new_keys = [key for key in keys if eval(filter_text, {}, {'key': key, 'ts': ts})]
    print(f'Filtered keys: {len(keys)} -> {len(new_keys)} ({len(keys) - len(new_keys)} keys removed)')
    return new_keys


def keys_filtering_loop(keys):
    # ask if you should filter?
    while (filter_text := input('Enter filter text (hit enter to skip):')):
        # evaluate filter
        try:
            keys = filter_keys(keys, filter_text)
        except Exception as e:
            print(f'Error: {e}')
            continue

    return keys


def arg_parser():
    import argparse
    parser = argparse.ArgumentParser(description='Copy keys from one Redis to another.')
    parser.add_argument('--pattern', type=str, help='Key pattern to match keys to copy')
    parser.add_argument('--filter', type=str, help='Filter keys')
    parser.add_argument('-y', action='store_true', help='Skip confirmation')
    return parser.parse_args()


def main():
    # Get source Redis credentials from environment variables
    if not (src_redis := get_redis('SRC')):
        return

    # Get destination Redis credentials from environment variables
    if not (dst_redis := get_redis('DST')):
        return

    args = arg_parser()

    # Pattern to match keys
    key_pattern = args.pattern or input('Enter key pattern:')
    key_pattern = key_pattern.strip()
    if not key_pattern:
        print('Invalid key pattern.')
        return

    keys = analise_keys(src_redis, key_pattern)
    if not keys:
        print('No keys found matching the pattern.')
        return

    if args.filter:
        keys = filter_keys(keys, args.filter)
    else:
        keys = keys_filtering_loop(keys)

    if len(keys) == 0:
        print('No keys to copy.')
        return

    if not args.y:
        # confirmations
        print_them = len(keys) < 100 or input(f'Print {len(keys)} keys? y/N').upper().strip() == 'Y'
        if print_them:
            print('Keys to copy:')
            pprint(keys)

        if input('Are you sure? y/N?').upper().strip() != 'Y':
            print('Abort!')
            return

    # Copy keys from source to destination
    copy_keys(src_redis, dst_redis, keys)
    print(f"Keys matching pattern '{key_pattern}' have been copied from source to destination Redis.")


if __name__ == "__main__":
    main()
