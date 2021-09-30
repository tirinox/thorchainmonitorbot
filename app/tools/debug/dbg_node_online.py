import asyncio

from services.jobs.fetch.base import INotified
from services.jobs.fetch.thormon import ThorMonWSSClient
from services.models.thormon import ThorMonAnswer
from services.lib.depcont import DepContainer
from services.lib.utils import sep
from services.notify.personal.node_online import NodeOnlineTracker
from tools.lib.lp_common import LpAppFramework


class ThorMonListenerTest(INotified):
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.thor_mon = ThorMonWSSClient(deps.cfg.network_id)
        self.online_tracker = NodeOnlineTracker(deps)
        self.known_nodes = []

    async def prepare(self):
        self.thor_mon.subscribe(self)
        asyncio.create_task(self.thor_mon.listen_forever())

    async def on_data(self, sender, data):
        if isinstance(data, ThorMonAnswer):
            if data.nodes:
                print('Got message from THORMon')
                self.known_nodes = [n.node_address for n in data.nodes]
                await self.online_tracker.telemetry_db.write_telemetry(data)


async def my_test_node_online_telemetry():
    lp_app = LpAppFramework()
    thor_mon = ThorMonListenerTest(lp_app.deps)
    async with lp_app:
        await thor_mon.prepare()
        while True:
            sep()
            # profile = await thor_mon.online_tracker.get_online_profiles(thor_mon.known_nodes)
            # if profile:
            #     print('Online profile:')
            #     profile1 = next(iter(profile.values()))
            #     print(profile1)
            await asyncio.sleep(5.0)


async def main():
    await my_test_node_online_telemetry()


if __name__ == '__main__':
    asyncio.run(main())
