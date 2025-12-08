import asyncio
import logging

from jobs.scanner.native_scan import BlockScanner
from tools.lib.lp_common import LpAppFramework


def find_pattern_json(data, pattern, path=""):
    """
    Recursively search for dictionaries in `data` that contain all key-value pairs from `pattern`,
    and return their paths.

    :param data: The JSON-like data structure (dict or list).
    :param pattern: The dictionary pattern to search for.
    :param path: The current path in the data structure.
    :return: A generator yielding (path, matching_dict) tuples.
    """
    if isinstance(data, dict):
        # Check if current dictionary contains the pattern
        if all(k in data and data[k] == v for k, v in pattern.items()):
            yield path, data
        # Recur for all values in the dictionary
        for key, value in data.items():
            new_path = f"{path}.{key}" if path else key
            yield from find_pattern_json(value, pattern, new_path)
    elif isinstance(data, list):
        # Recur for all elements in the list
        for index, item in enumerate(data):
            new_path = f"{path}[{index}]"
            yield from find_pattern_json(item, pattern, new_path)


async def dbg_find_outbounds(app, tx_id, start_block_index):
    d = app.deps
    block_index = start_block_index

    while True:
        print(f"Scanning block {block_index}...")
        block_raw = await d.thor_connector.query_thorchain_block_raw(block_index)

        for match in find_pattern_json(block_raw, {
            "type": "outbound",
            "in_tx_id": tx_id,
        }):
            path, match = match
            print(f"[#{block_index}:010] Found match at {path}: {match}")

        block_index += 1

async def run():
    app = LpAppFramework(log_level=logging.INFO)
    async with app:
        # await dbg_find_outbounds(app, "0F77D9743C8FE2557A2DBD48E59BBA1CAD9B9B771ED1111AB7E6632EEF1584FA", 19711750)
        await dbg_find_outbounds(app, "0F77D9743C8FE2557A2DBD48E59BBA1CAD9B9B771ED1111AB7E6632EEF1584FA", 19711750)


if __name__ == '__main__':
    asyncio.run(run())
