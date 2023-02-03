import asyncio
import random

from services.lib.date_utils import now_ts
from services.lib.scheduler import Scheduler
from tools.lib.lp_common import LpAppFramework, Receiver


async def handler(sender, data):
    print(f'handler called: {data}')


async def demo_run_scheduler_simple_1(sched: Scheduler):
    for i in range(20):
        delay = random.randint(1, 20)
        await sched.schedule(f'random-{i}', now_ts() + delay)
    await sched.schedule('periodic', period=2)
    await sched.run()


async def demo_run_scheduler_simple_2_per(sched: Scheduler):
    # fixme: data is a key!! key must be unique. store period and other data somewhere else
    await sched.schedule('1', now_ts() + 1.0, period=5)
    await sched.schedule('2', now_ts() + 1.5, period=5.1)
    await sched.run()


async def run():
    app = LpAppFramework()
    async with app(brief=True):
        r = await app.deps.db.get_redis()
        sched = Scheduler(r, 'demo', poll_interval=1)
        sched.add_subscriber(Receiver(tag='scheduler-demo', callback=handler))

        await sched.cancel_all_periodic()

        await demo_run_scheduler_simple_1(sched)
        # await demo_run_scheduler_simple_2_per(sched)


if __name__ == '__main__':
    asyncio.run(run())
