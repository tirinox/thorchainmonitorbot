import asyncio

from models.sched import SchedJobCfg, IntervalCfg
from notify.pub_configure import configure_scheduled_public_notifications
from tools.lib.lp_common import LpAppFramework


async def dbg_run_public_scheduler(app: LpAppFramework):
    p = await configure_scheduled_public_notifications(app.deps)

    async def foo_job():
        print("Foo job executed")

    await p.register_job_type('foo_job', foo_job)

    p.start()

    await p.add_new_job(SchedJobCfg(
        id="dbg_foo_job",
        func="foo_job",
        enabled=True,
        variant="interval",
        interval=IntervalCfg(seconds=3),
        max_instances=1,
        coalesce=True,
    ))

    await p.apply_scheduler_configuration()


async def main():
    app = LpAppFramework()
    async with app:
        await dbg_run_public_scheduler(app)
        await asyncio.sleep(10_000)


if __name__ == '__main__':
    asyncio.run(main())
