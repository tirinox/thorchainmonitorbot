import asyncio

from notify.pub_configure import configure_scheduled_public_notifications
from notify.pub_scheduler import PublicScheduler
from tools.lib.lp_common import LpAppFramework


async def dbg_run_public_scheduler(app: LpAppFramework):
    p = await configure_scheduled_public_notifications(app.deps)
    p.start()

    await p.register_job('foo_job', lambda: print("Debug job executed"))


async def main():
    app = LpAppFramework()
    async with app:
        await dbg_run_public_scheduler(app)
        await asyncio.sleep(10_000)

if __name__ == '__main__':
    asyncio.run(main())
