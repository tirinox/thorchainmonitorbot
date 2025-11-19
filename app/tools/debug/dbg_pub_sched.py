import asyncio

from models.sched import SchedJobCfg, IntervalCfg, CronCfg
from notify.pub_configure import configure_scheduled_public_notifications
from tools.lib.lp_common import LpAppFramework


async def dbg_run_public_scheduler(app: LpAppFramework):
    p = await configure_scheduled_public_notifications(app.deps)

    async def foo_job():
        print("Foo job executed")

    async def failing_job():
        print("Failing job executed")
        raise Exception("Intentional failure for testing")

    await p.register_job_type('foo_job', foo_job)
    await p.register_job_type('failing_job', failing_job)

    p.start()

    await p.add_new_job(SchedJobCfg(
        id="dbg_foo_job",
        func="foo_job",
        enabled=True,
        variant='cron',
        cron=CronCfg(
            second='*/15',
            minute='41-59'
        )
    ))

    await p.add_new_job(SchedJobCfg(
        id="dbg_failing_job",
        func="failing_job",
        enabled=True,
        variant="interval",
        interval=IntervalCfg(seconds=10),
    ))

    await p.apply_scheduler_configuration()


async def main():
    app = LpAppFramework()
    async with app:
        await dbg_run_public_scheduler(app)
        await asyncio.sleep(10_000)


if __name__ == '__main__':
    asyncio.run(main())
