import asyncio
from typing import Dict

from aiothornode.types import ThorNodeAccount

from services.lib.delegates import INotified
from services.jobs.fetch.thormon import ThorMonWSSClient
from services.lib.depcont import DepContainer
from services.lib.utils import sep
from services.models.thormon import ThorMonAnswer
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
                # await self.online_tracker.telemetry_db.write_telemetry(data)


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


def gen_chain_height_dic(node: ThorNodeAccount):
    return {c['chain']: c['height'] for c in node.observe_chains} if node and node.observe_chains else {}


def process_node_map(prev_node_map: Dict[str, ThorNodeAccount], curr_node_map: Dict[str, ThorNodeAccount]):
    sep()
    for node_address, prev_node in prev_node_map.items():
        curr_node = curr_node_map.get(node_address)
        if curr_node and prev_node:
            curr_chains = gen_chain_height_dic(curr_node)
            prev_chains = gen_chain_height_dic(prev_node)
            if curr_chains != prev_chains:
                print(f'{node_address} chain data update')
                for chain, height in curr_chains.items():
                    prev_height = int(prev_chains.get(chain, 0))
                    height = int(height)
                    delta = height - prev_height
                    if delta:
                        print(f'-- {chain}: {prev_height} => {height} = {delta} blocks')
        else:
            print(f'{node_address} there is one piece of data is absent')


async def my_chain_height_update_check():
    lp_app = LpAppFramework()
    async with lp_app:
        prev_node_map = {}
        while True:
            nodes = await lp_app.deps.thor_connector.query_node_accounts()

            node_map = {node.node_address: node for node in nodes if node.node_address}
            if not node_map:
                continue

            if prev_node_map:
                process_node_map(prev_node_map, node_map)

            prev_node_map = node_map

            await asyncio.sleep(1.0)


async def main():
    # await my_test_node_online_telemetry()
    await my_chain_height_update_check()


if __name__ == '__main__':
    asyncio.run(main())
