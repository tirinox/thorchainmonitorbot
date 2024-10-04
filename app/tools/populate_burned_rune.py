"""
This script helps you to restore the historical burned rune data from the blockchain.
All existing data will be removed and replaced with the new one.

Instruction:

When in the container:
    $ make attach
    $ PYTHONPATH="/app" python tools/populate_burned_rune.py /config/config.yaml

When developing locally:
    $ cd app
    $ PYTHONPATH="." python tools/populate_burned_rune.py --days 10 --time_step 3600

"""
import argparse
import asyncio
import sys

from lib.date_utils import HOUR, DAY
from notify.public.burn_notify import BurnNotifier
from tools.lib.lp_common import LpAppFramework

DAYS_TO_RESTORE = 10
TIME_STEP = HOUR / 2


async def run():
    parser = argparse.ArgumentParser(description='Burned rune data population script')

    # Add arguments
    parser.add_argument('--days', type=int, default=DAYS_TO_RESTORE,
                        help='Number of days to restore (default: 10)')
    parser.add_argument('--time_step', type=float, default=TIME_STEP,
                        help='Time step in seconds (default: HOUR / 2)')
    # add positional arguments
    parser.add_argument('config', type=str, help='Path to the configuration file')

    # Parse the arguments
    args = parser.parse_args()
    print(f'Arguments: {args}')

    # clear argv
    sys.argv = sys.argv[:1]
    sys.argv.append(args.config)
    app = LpAppFramework()

    # wish to continue?
    print()
    if input('Do you wish to continue (y/N)? ').strip().lower() != 'y':
        print('Aborted')
        return

    async with app(brief=True):
        await app.deps.last_block_fetcher.run_once()
        await app.deps.mimir_const_fetcher.run_once()
        await app.deps.pool_fetcher.run_once()

        notifier = BurnNotifier(app.deps)
        await notifier.erase_and_populate_from_history(
            period=args.time_step,
            max_points=args.days * DAY / TIME_STEP
        )


if __name__ == '__main__':
    asyncio.run(run())
