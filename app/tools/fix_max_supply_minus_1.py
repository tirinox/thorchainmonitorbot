"""
    This script connects to the remote Redis server in order to remove
    all entries from time series "ts-stream:RuneMaxSupply" which contain invalid "max_supply" e.i. "-1"
"""
import json
import os

from dotenv import load_dotenv

from tools.lib.remote_redis import get_redis

KEY = 'ts-stream:RuneMaxSupply'

# Load environment variables from .env file
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), 'redis_copy_keys.env'))


def main(dry_run=True):
    """
    Connects to Redis and removes invalid entries from the specified stream.

    Args:
        dry_run (bool): If True, only simulates the removal of invalid entries without deleting them.
    """
    # Get source Redis credentials from environment variables
    if not (r := get_redis('SRC')):
        print("Failed to connect to Redis")
        return

    # Get the number of items in the stream
    n = r.xlen(KEY)
    print(f'{KEY} contains {n} entries')

    # Iterate over all entries
    cursor = 0
    count_removed = 0

    total_count = 0
    while True:
        # Fetch 100 entries at a time starting from the cursor
        entries = r.xread({KEY: cursor}, count=100)
        if not entries:
            break

        for stream, records in entries:
            print('.', end='')
            for entry_id, entry_data in records:
                try:
                    if entry_data.get("max_supply") == -1:
                        if dry_run:
                            print(f"[Dry Run] Would remove entry {entry_id}")
                        else:
                            r.xdel(KEY, entry_id)
                            print(f"Removed entry {entry_id}")
                        count_removed += 1
                except KeyError:
                    print(f"Missing 'data' key in entry {entry_id}")
                except json.JSONDecodeError:
                    print(f"Invalid JSON format in entry {entry_id}: {entry_data}")
                except Exception as e:
                    print(f"Error processing entry {entry_id}: {e}")

                total_count += 1
                if total_count % 1000 == 0:
                    print(total_count)

            # Update the cursor to continue iterating
            cursor = records[-1][0]

    print(
        f"{'Simulated removal of' if dry_run else 'Removed'} {count_removed} invalid entries with 'max_supply' = '-1'")


if __name__ == "__main__":
    # Modify dry_run to False to enable actual deletion
    main(dry_run=True)
