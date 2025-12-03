import asyncio

from notify.pub_configure import PublicAlertJobExecutor
from tools.lib.lp_common import LpAppFramework


async def dbg_run_one_job(app: LpAppFramework):
    ex: PublicAlertJobExecutor = app.deps.pub_alert_executor
    # await ex.job_pol_summary()
    # await ex.job_runepool_summary()
    # await ex.job_top_pools()
    await ex.job_supply_chart()


async def main():
    app = LpAppFramework()
    async with app():
        await dbg_run_one_job(app)
        await asyncio.sleep(10)


if __name__ == '__main__':
    asyncio.run(main())
