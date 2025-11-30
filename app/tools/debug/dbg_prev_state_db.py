import asyncio

from notify.pub_configure import PublicAlertJobExecutor
from tools.lib.lp_common import LpAppFramework


async def dbg_pol_run_job(app: LpAppFramework):
    ex: PublicAlertJobExecutor = app.deps.pub_alert_executor
    await ex.job_pol_summary()


async def dbg_runepool_run_job(app: LpAppFramework):
    ex: PublicAlertJobExecutor = app.deps.pub_alert_executor
    await ex.job_runepool_summary()


async def main():
    app = LpAppFramework()
    async with app():
        # await dbg_pol_run_job(app)
        await dbg_runepool_run_job(app)


if __name__ == '__main__':
    asyncio.run(main())
