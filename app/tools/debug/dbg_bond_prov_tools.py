import asyncio

from services.jobs.node_churn import NodeChurnDetector
from services.notify.personal.bond_provider import PersonalBondProviderNotifier
from tools.lib.lp_common import LpAppFramework


async def demo_run_continuously(app: LpAppFramework):
    d = app.deps

    churn_detector = NodeChurnDetector(d)
    d.node_info_fetcher.add_subscriber(churn_detector)

    bond_provider_tools = PersonalBondProviderNotifier(d)
    churn_detector.add_subscriber(bond_provider_tools)

    await d.node_info_fetcher.run()


async def main():
    app = LpAppFramework()
    async with app():
        await demo_run_continuously(app)


if __name__ == '__main__':
    asyncio.run(main())
