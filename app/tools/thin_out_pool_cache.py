"""
Thins out the history cache of pool states (KeyDB hash PoolInfo:hashtable_v2):
deletes entries so that the remaining ones are at least --min-distance blocks apart.

Usage:
    make thin-out-pool-cache                          # asks before deleting
    make thin-out-pool-cache MIN_DISTANCE=50 YES=1    # no questions
    make thin-out-pool-cache DRY_RUN=1                # only count

    or inside the container (make attach):
    PYTHONPATH="/app" python tools/thin_out_pool_cache.py /config/config.yaml --min-distance 10 --yes

Every option may also come from the environment: THIN_OUT_MIN_DISTANCE, THIN_OUT_SCAN_BATCH_SIZE,
THIN_OUT_MAX_KEYS_TO_SCAN, THIN_OUT_YES, THIN_OUT_DRY_RUN. Command line arguments win.
"""
import argparse
import asyncio
import logging
import os

from jobs.fetch.pool_price import PoolFetcher
from tools.lib.lp_common import LpAppFramework, ask_yes_no


def env_flag(name):
    return os.environ.get(name, '').strip().lower() in ('1', 'true', 'yes', 'y')


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description='Thin out the pool history cache.')
    # the config path is read by Config from sys.argv[1]; it is declared here only to keep argparse happy
    parser.add_argument('config', nargs='?', help='path to config.yaml')
    parser.add_argument('--min-distance', type=int,
                        default=int(os.environ.get('THIN_OUT_MIN_DISTANCE', 10)),
                        help='minimum distance between the remaining entries, blocks (default 10)')
    parser.add_argument('--scan-batch-size', type=int,
                        default=int(os.environ.get('THIN_OUT_SCAN_BATCH_SIZE', 10000)),
                        help='HSCAN batch size (default 10000)')
    parser.add_argument('--max-keys-to-scan', type=int,
                        default=int(os.environ.get('THIN_OUT_MAX_KEYS_TO_SCAN', 0)),
                        help='stop scanning after that many keys, 0 = scan everything (default 0)')
    parser.add_argument('-y', '--yes', action='store_true', default=env_flag('THIN_OUT_YES'),
                        help='delete without asking')
    parser.add_argument('--dry-run', action='store_true', default=env_flag('THIN_OUT_DRY_RUN'),
                        help='only count the entries to delete')
    args = parser.parse_args(argv)
    if args.min_distance < 2:
        parser.error('--min-distance must be at least 2')
    return args


async def thin_out_pool_cache(app, args):
    pf: PoolFetcher = app.deps.pool_fetcher

    keys = await pf.cache.get_thin_out_keys(
        min_distance=args.min_distance,
        scan_batch_size=args.scan_batch_size,
        max_keys_to_scan=args.max_keys_to_scan or None,
    )
    print(f"Total keys to delete: {len(keys)} (min distance = {args.min_distance} blocks)")

    if args.dry_run:
        print("Dry run. No keys deleted.")
        return

    if not keys:
        print("Nothing to delete.")
        return

    if args.yes or ask_yes_no(f"Do you want to delete {len(keys)} keys?", default=False):
        await pf.cache.delete_keys_batched(keys)
        print(f"Deleted {len(keys)} keys.")
    else:
        print("No keys deleted.")


async def main():
    args = parse_args()
    app = LpAppFramework(log_level=logging.INFO)
    async with app:
        await thin_out_pool_cache(app, args)


if __name__ == '__main__':
    asyncio.run(main())
