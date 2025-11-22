import asyncio
import random

from models.sched import SchedJobCfg, IntervalCfg, CronCfg
from notify.pub_configure import configure_scheduled_public_notifications
from tools.lib.lp_common import LpAppFramework


async def dbg_run_public_scheduler(app: LpAppFramework):
    p = await configure_scheduled_public_notifications(app.deps)

    async def foo_job():
        await app.send_test_tg_message(f"🤓 Normal Foo job executed successfully!")

    async def failing_job():
        if random.uniform(0, 1) > 0.3:
            await app.send_test_tg_message(f'⚠️ Failing job encountered an error!')
            raise Exception("Intentional failure for testing")
        else:
            await app.send_test_tg_message(f'✅ Failing job succeeded this time!')

    await p.register_job_type('foo_job', foo_job)
    await p.register_job_type('failing_job', failing_job)

    await p.start()

    await p.add_new_job(SchedJobCfg(
        id="dbg_foo_job",
        func="foo_job",
        enabled=True,
        variant='cron',
        cron=CronCfg(
            second='*/30',
            minute='20-40'
        )
    ), allow_replace=True)

    await p.add_new_job(SchedJobCfg(
        id="dbg_failing_job",
        func="failing_job",
        enabled=True,
        variant="interval",
        interval=IntervalCfg(seconds=60),
    ), allow_replace=True)

    await p.db_log.warning("start_debug_script", data="foo")

    await p.apply_scheduler_configuration()


async def main():
    app = LpAppFramework()
    async with app:
        await dbg_run_public_scheduler(app)
        await asyncio.sleep(10_000)


if __name__ == '__main__':
    asyncio.run(main())
