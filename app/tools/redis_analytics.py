# Instruction:
# $ make attach
# $ PYTHONPATH="/app" python tools/redis_analytics.py /config/config.yaml
import asyncio
from dataclasses import dataclass, field
import heapq
import logging

import tqdm
from redis.asyncio import Redis

from lib.texts import sep
from tools.lib.lp_common import LpAppFramework


@dataclass
class _KeyNode:
    children: dict[str, "_KeyNode"] = field(default_factory=dict)
    is_key: bool = False
    leaf_count: int = 0


def _compute_leaf_counts(node: _KeyNode) -> int:
    total = 1 if node.is_key else 0
    for child in node.children.values():
        total += _compute_leaf_counts(child)
    node.leaf_count = total
    return total


def _print_branch_counts(node: _KeyNode, indent: str = "", min_leaves=10):
    if node.leaf_count < min_leaves:
        # print(f"{indent}﹂* (leaves: {node.leaf_count})")
        pass
    else:
        for part, child in sorted(node.children.items()):
            if child.children:
                print(f"{indent}﹂{part} (leaves: {child.leaf_count})")
                _print_branch_counts(child, indent + "  ", min_leaves=min_leaves)


async def calculate_number_of_elements(r, top_n=100, scan_count=10000):
    logging.info('Streaming keys from DB via SCAN')
    results_heap = []  # min-heap of (data_len, key, key_type)
    types = set()
    total_keys = 0
    progress = tqdm.tqdm(desc='Keys processed', unit='key')

    async for key in r.scan_iter(count=scan_count):
        total_keys += 1
        progress.update(1)

        key_type = await r.type(key)
        if isinstance(key_type, bytes):
            key_type = key_type.decode()

        if key_type == 'none':
            await asyncio.sleep(0.1)
            key_type = await r.type(key)
            if isinstance(key_type, bytes):
                key_type = key_type.decode()

        if key_type == 'hash':
            data_len = await r.hlen(key)
        elif key_type == 'set':
            data_len = await r.scard(key)
        elif key_type == 'zset':
            data_len = await r.zcard(key)
        elif key_type == 'stream':
            data_len = await r.xlen(key)
        elif key_type == 'string':
            data_len = 1
        elif key_type == 'list':
            data_len = await r.llen(key)
        elif key_type == 'none':
            continue
        else:
            logging.warning(f'Unknown type {key_type} for key {key}')
            data_len = 1

        types.add(key_type)
        heapq.heappush(results_heap, (data_len, key, key_type))
        if len(results_heap) > top_n:
            heapq.heappop(results_heap)

    progress.close()
    logging.info(f'Processed {total_keys} keys; Types: {types}')

    results = sorted(results_heap, key=lambda x: x[0], reverse=True)
    for i, (data_len, key, key_type) in enumerate(results, start=1):
        print(f'{i: 4}. ({data_len: 6} items): {key} (dt={key_type})')


async def key_hierarchy(r: Redis):
    root = _KeyNode()
    async for key in r.scan_iter(count=10000):
        if isinstance(key, bytes):
            key = key.decode()
        parts = key.split(':')
        current = root
        for part in parts:
            current = current.children.setdefault(part, _KeyNode())
        current.is_key = True

    total_leaves = _compute_leaf_counts(root)
    if total_leaves == 0:
        logging.info('No keys found while building hierarchy')
        return

    print('Key hierarchy (branch -> leaf count):')
    _print_branch_counts(root)
    print(f'Total leaf keys: {total_leaves}')


async def main():
    app = LpAppFramework(log_level=logging.INFO)
    async with app:
        r = await app.deps.db.get_redis()
        await calculate_number_of_elements(r, top_n=30)
        sep()
        await key_hierarchy(r)


if __name__ == "__main__":
    asyncio.run(main())
