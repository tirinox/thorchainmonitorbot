import asyncio
import logging

from services.lib.accumulator import Accumulator
from services.lib.config import Config
from services.lib.date_utils import MINUTE, HOUR, now_ts
from services.lib.db import DB
from services.models.time_series import PriceTimeSeries, TimeSeries


async def try_buckets(db):
    now = now_ts()
    ts = TimeSeries('Test', db)
    await ts.add(ts.discrete_message_id(now, HOUR))


async def get_clear_test_accum(db):
    a = Accumulator('test', db, tolerance=2)
    n_deleted = await a.clear()
    print(f'{n_deleted = }')
    return a


async def fill_accum(a, n=10, delay=0.01, x=None):
    for i in range(n):
        v = x if x else i * 10
        await a.add_now(swap=v)
        r = await a.get()
        print(r)
        await asyncio.sleep(delay)
    print('------- fill completed -------')


async def try_accum(db):
    a = await get_clear_test_accum(db)
    await fill_accum(a, 20, 0.23)
    range_results = await a.get_range(-10)
    print(range_results)


async def try_accum_clear_before(db):
    a = await get_clear_test_accum(db)
    await fill_accum(a, 10, 0.5)
    n1 = len(await a.all_my_keys())
    print(f'{n1 = }')

    await a.clear(before=now_ts() - 2)

    n2 = len(await a.all_my_keys())
    print(f'{n2 = }')


async def main(db):
    await db.get_redis()
    await try_accum_clear_before(db)


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    cfg = Config()
    db = DB(loop)

    asyncio.run(main(db))
