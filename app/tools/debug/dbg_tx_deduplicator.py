import asyncio
import secrets

from redis import ResponseError
from tqdm import tqdm

from lib.utils import sizeof_fmt
from notify.dup_stop import TxDeduplicator
from tools.lib.lp_common import LpAppFramework


def random_hash():
    return secrets.token_hex(32)


N = 10 ** 6
CAPACITY = 10 ** 8
ERROR_RATE = 0.01


async def collect_info_about_existing_dedup(app):
    r = await app.deps.db.get_redis()
    keys = await r.keys('tx:dedup_v2:*')
    print(keys)
    for key in keys:
        try:
            length = await r.strlen(key)
            print(f'Key {key} length = {length} bytes or {sizeof_fmt(length)}')
        except ResponseError as e:
            pass


async def dbg_accuracy_benchmark(app: LpAppFramework):
    dedup = TxDeduplicator(app.deps.db, 'dbg:test1', capacity=CAPACITY, error_rate=ERROR_RATE)
    print(f'Initialized deduplicator {dedup.key} size = {dedup.size}')
    input()
    real_heap = set()
    await dedup.clear()
    false_positives = 0
    false_negatives = 0
    for _ in tqdm(range(N)):
        h = random_hash()
        seen = await dedup.have_ever_seen_hash(h)
        if seen and not h in real_heap:
            print(f'Error: false positive on first check for {h}')
            false_positives += 1
        if not seen and h in real_heap:
            print(f'Error: false negative on first check for {h}')
            false_negatives += 1
        real_heap.add(h)
    print(f'False positives after first check: {false_positives}/{N} ({false_positives / N * 100:.4f}%)')
    print(f'False negatives after first check: {false_negatives}/{N} ({false_negatives / N * 100:.4f}%)')


async def main():
    app = LpAppFramework()
    async with app:
        # await collect_info_about_existing_dedup(app)
        await dbg_accuracy_benchmark(app)


if __name__ == '__main__':
    asyncio.run(main())
