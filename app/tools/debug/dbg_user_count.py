import asyncio
import logging
import random

from redis.asyncio import Redis

from jobs.scanner.native_scan import BlockScanner
from jobs.user_counter import UserCounterMiddleware
from lib.active_users import DailyActiveUserCounter, ManualUserCounter
from lib.date_utils import DAY, now_ts
from lib.utils import random_hex
from tools.lib.lp_common import LpAppFramework


async def benchmark_accuracy_of_hyper_log_log(lp_app: LpAppFramework):
    k = 'TestHyperLogLog'
    n = 100000
    r: Redis = await lp_app.deps.db.get_redis()
    await r.delete(k)
    for i in range(n):
        await r.pfadd(k, f'user{i}')
    r_n = await r.pfcount(k)
    print(f'{n = }, {r_n = }.')


async def dau_counter(app: LpAppFramework):
    d = DailyActiveUserCounter(app.deps.db.redis, 'TestDau')
    await d.clear()
    return d


async def play_dau(app):
    dau = await dau_counter(app)
    await dau.clear()
    mau_before = await dau.get_mau()
    print(f'{mau_before = }')

    await dau.hit(users=['u1', 'u2'])
    mau_after = await dau.get_mau()
    print(f'{mau_after = }')

    wau = await dau.get_wau()
    print(f'{wau = }, add u3 10 days before')
    await dau.hit(user='u3', now=now_ts() - 10 * DAY)
    wau = await dau.get_wau()
    print(f'{wau = }, add u3')


async def auto_play_dau(app):
    dau = await dau_counter(app)

    manual = ManualUserCounter()
    n = 50000
    max_user = 1000000
    max_ago = 40 * DAY
    now = now_ts()

    tested = [dau, manual]

    for _ in range(n):
        upper = random.randint(1, max_user + 1)
        p = random.randint(1, upper)
        user = f'a_user_{p}'
        ts = random.randint(int(now - max_ago), int(now))
        for testee in tested:
            await testee.hit(user=user, now=ts)

    for testee in tested:
        dau = await testee.get_dau_yesterday()
        wau = await testee.get_wau()
        mau = await testee.get_mau()
        print(f'{testee.__class__.__name__}: {dau = }, {wau = }, {mau = }')


async def real_life_active_scan_user_counter(app: LpAppFramework):
    scanner = BlockScanner(app.deps)
    user_counter = UserCounterMiddleware(app.deps)
    scanner.add_subscriber(user_counter)
    await scanner.run()


async def demo_unique_users_of_block(app: LpAppFramework):
    user_counter = UserCounterMiddleware(app.deps)
    scanner = BlockScanner(app.deps)

    r = await scanner.fetch_one_block(7499377)  # donate
    print('donate:', user_counter.get_unique_users(r))

    r = await scanner.fetch_one_block(8700682)  # has 3 observed BTC tx ins
    print('observed_in:', user_counter.get_unique_users(r))

    r = await scanner.fetch_one_block(8700092)  # switch
    print('switch:', user_counter.get_unique_users(r))

    r = await scanner.fetch_one_block(8701069)  # synth
    print('synth:', user_counter.get_unique_users(r))


async def demo_display_user_stats(app: LpAppFramework):
    counter = UserCounterMiddleware(app.deps)

    # definitely it is the week before
    await counter.counter.hit(
        user='thorFakeUser', now=now_ts() - 10 * DAY
    )

    stats = await counter.get_main_stats()
    print(stats)


async def demo_simulate_users(app: LpAppFramework):
    counter = DailyActiveUserCounter(app.deps.db.redis, '_Test')
    await counter.clear()

    for day in range(30):
        ts = now_ts() - day * DAY
        user_count = 31 - day
        users = [f'thor1{random_hex(20).decode()}' for i in range(user_count)]
        print(f'day from now = {day}, users = {len(users)}')

        await counter.hit(users=users, now=ts)

    stats = await counter.get_stats()
    print(stats)


async def main():
    lp_app = LpAppFramework(log_level=logging.INFO)
    async with lp_app(brief=True):
        # await benchmark_accuracy_of_hyper_log_log(lp_app)
        # await play_dau(lp_app)
        # await auto_play_dau(lp_app)
        await real_life_active_scan_user_counter(lp_app)
        # await demo_unique_users_of_block(lp_app)
        # await demo_display_user_stats(lp_app)
        # await demo_simulate_users(lp_app)

if __name__ == '__main__':
    asyncio.run(main())
