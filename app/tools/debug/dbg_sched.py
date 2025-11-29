import asyncio
import random

from lib.date_utils import now_ts
from lib.scheduler import PrivateScheduler
from tools.lib.lp_common import LpAppFramework, Receiver


async def handler(sender, data):
    print(f'handler called: {data}')


async def demo_run_scheduler_simple_1(sched: PrivateScheduler):
    for i in range(20):
        delay = random.randint(1, 20)
        await sched.schedule(f'random-{i}', now_ts() + delay)
    await sched.schedule('periodic', period=2)
    await sched.run()


async def demo_run_scheduler_simple_2_per(sched: PrivateScheduler):
    await sched.schedule('1', now_ts() + 1.0, period=5)
    await sched.schedule('2', now_ts() + 1.5, period=5.1)
    await sched.run()


async def demo_cancel_periodic_3(sched: PrivateScheduler):
    await sched.schedule('Troll', period=1)

    async def cancel_guy():
        await asyncio.sleep(3)
        await sched.cancel('Troll')

    asyncio.create_task(cancel_guy())  # in background
    await sched.run()


async def demo_ignore_old_4(sched: PrivateScheduler):
    sched.forget_after = 1

    await sched.schedule('Old', now_ts() + 2)
    await sched.schedule('WillFire', now_ts() + 5)

    print('Sleeping 4 seconds...')
    await asyncio.sleep(4)

    print('Run!')
    await sched.run()


async def run():
    app = LpAppFramework()
    async with app(brief=True):
        r = await app.deps.db.get_redis()
        sched = PrivateScheduler(r, 'demo', poll_interval=1)
        sched.add_subscriber(Receiver(tag='scheduler-demo', callback=handler))

        await sched.cancel_all_periodic()

        # await demo_run_scheduler_simple_1(sched)
        # await demo_run_scheduler_simple_2_per(sched)
        # await demo_cancel_periodic_3(sched)
        await demo_ignore_old_4(sched)


if __name__ == '__main__':
    asyncio.run(run())
