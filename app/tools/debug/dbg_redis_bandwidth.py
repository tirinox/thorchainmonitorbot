import asyncio
import logging
import random

from services.lib.date_utils import now_ts
from services.lib.utils import setup_logs
from services.lib.texts import sep
from tools.lib.lp_common import LpAppFramework


async def bandwidth_test(app: LpAppFramework):
    start = now_ts()
    n_op = 10000
    r = app.deps.db.redis
    for _ in range(n_op):
        key1 = f'key.{random.randint(0, 10000)}'
        key2 = f'key.{random.randint(0, 10000)}'
        key3 = f'key.{random.randint(0, 10000)}'
        await asyncio.gather(
            r.get(key1),
            r.set(key2, '?' * random.randint(10, 1000)),
            r.delete(key3)
        )

    sep()
    dt = now_ts() - start
    op_sec = 3 * n_op / dt
    print(f'Bandwidth = {op_sec:.3f} op/sec')
    sep()


async def online_data_test(app: LpAppFramework):
    ...


async def run():
    app = LpAppFramework()
    await app.prepare(brief=True)
    await online_data_test(app)


if __name__ == '__main__':
    setup_logs(logging.DEBUG)
    asyncio.run(run())
