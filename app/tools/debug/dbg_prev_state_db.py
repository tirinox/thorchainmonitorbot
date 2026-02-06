import asyncio

from lib.texts import sep
from notify.pub_configure import PublicAlertJobExecutor
from notify.pub_scheduler import PublicScheduler
from tools.lib.lp_common import LpAppFramework


async def dbg_run_all_jobs(app: LpAppFramework):
    ex: PublicAlertJobExecutor = app.deps.pub_alert_executor
    for call in ex.AVAILABLE_TYPES.values():
        sep()
        await app.deps.broadcaster.broadcast_to_all("debug", '------')
        await call(ex)


async def dbg_run_one_job(app: LpAppFramework):
    ex: PublicAlertJobExecutor = app.deps.pub_alert_executor
    # await ex.job_pol_summary()
    # await ex.job_runepool_summary()
    # await ex.job_top_pools()
    # await ex.job_supply_chart()
    # await ex.job_trade_account_summary()
    # await ex.job_rune_burn_chart()
    # await ex.job_key_metrics()
    # await ex.job_tcy_summary()
    # await ex.job_secured_asset_summary()
    # await ex.job_rune_cex_flow()
    await ex.job_price_alert()


async def dbg_test_command(app: LpAppFramework):
    sched: PublicScheduler = app.deps.pub_scheduler
    await sched.start_rpc_client()
    result = await sched.post_command(sched.COMMAND_RUN_NOW, func='pol_summary')
    print(f'Command result: {result}')


async def main():
    app = LpAppFramework()
    async with app():
        # await dbg_run_one_job(app)
        # await asyncio.sleep(10)
        await dbg_test_command(app)


if __name__ == '__main__':
    asyncio.run(main())
