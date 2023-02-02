import asyncio
import random

from services.jobs.scheduler import Scheduler
from services.lib.date_utils import now_ts
from tools.lib.lp_common import LpAppFramework, Receiver


async def demo_run_scheduler_simple_1(sched: Scheduler):
    async def handler(sender, data):
        print(f'handler called: {data}')

    sched.add_subscriber(Receiver(tag='scheduler-demo', callback=handler))

    for i in range(20):
        delay = random.randint(1, 20)
        await sched.schedule(now_ts() + delay, {'index': i})

    await sched.run()


async def run():
    app = LpAppFramework()
    async with app(brief=True):
        r = await app.deps.db.get_redis()
        sched = Scheduler(r, 'demo', poll_interval=1)
        await demo_run_scheduler_simple_1(sched)


if __name__ == '__main__':
    asyncio.run(run())
