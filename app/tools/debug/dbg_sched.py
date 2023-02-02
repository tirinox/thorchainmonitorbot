import asyncio
import random

from services.jobs.scheduler import Scheduler
from services.lib.date_utils import now_ts
from tools.lib.lp_common import LpAppFramework


async def demo_run_scheduler_simple_1(sched: Scheduler):
    async def handler(data):
        print(f'handler called: {data}')

    sched.handler = handler

    for i in range(100):
        delay = random.randint(1, 100)
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
