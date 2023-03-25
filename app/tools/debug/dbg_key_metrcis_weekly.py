import asyncio
import logging

from services.jobs.fetch.key_stats import KeyStatsFetcher
from services.notify.types.key_metrics_notify import KeyMetricsNotifier
from tools.lib.lp_common import LpAppFramework


async def demo_load(app: LpAppFramework):
    f = KeyStatsFetcher(app.deps)
    await f.fetch()


async def demo_analyse(app: LpAppFramework):
    f = KeyStatsFetcher(app.deps)
    dummy = KeyMetricsNotifier(app.deps)
    f.add_subscriber(dummy)
    await f.run_once()


async def main():
    lp_app = LpAppFramework(log_level=logging.INFO)
    async with lp_app:
        await lp_app.prepare(brief=True)

        await demo_analyse(lp_app)


if __name__ == '__main__':
    asyncio.run(main())
