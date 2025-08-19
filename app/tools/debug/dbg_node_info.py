import asyncio
import random
from collections import Counter
from copy import copy
from typing import Optional, List

from semver import VersionInfo

from api.aionode.types import ThorNetwork
from comm.localization.languages import Language
from comm.localization.manager import LocalizationManager
from jobs.achievement.notifier import AchievementsNotifier
from jobs.fetch.base import BaseFetcher
from jobs.fetch.node_info import NodeInfoFetcher
from jobs.node_churn import NodeChurnDetector
from lib.depcont import DepContainer
from lib.texts import sep
from models.node_db import NodeStateDatabase
from models.node_info import NodeSetChanges, NodeVersionConsensus, NodeInfo, NetworkNodes
from models.version import AlertVersionUpgradeProgress, AlertVersionChanged
from notify.public.node_churn_notify import NodeChurnNotifier
from notify.public.version_notify import VersionNotifier
from tools.lib.churn_sim import DbgChurnSimulator
from tools.lib.lp_common import LpAppFramework


def localizations(lpgen: LpAppFramework):
    loc_man: LocalizationManager = lpgen.deps.loc_man

    locs = (
        loc_man.get_from_lang('eng'),
        loc_man.get_from_lang('rus'),
        loc_man.get_from_lang(Language.ENGLISH_TWITTER),
    )
    return locs


async def node_version_notification_check_progress(lpgen: LpAppFramework, data: NodeSetChanges):
    locs = localizations(lpgen)

    await lpgen.send_test_tg_message('------------------------------------')

    new_ver = '0.60.1'
    n_new = 0
    progress = 0.1  # 0..1
    for n in data.nodes_all:
        if random.uniform(0, 1) <= progress:
            n.version = new_ver
            n_new += 1

    ver_con = NodeVersionConsensus(
        n_new / len(data.active_only_nodes),
        VersionInfo.parse(new_ver),
        n_new,
        len(data.active_only_nodes)
    )

    for loc in locs:
        sep()
        msg = loc.notification_text_version_changed_progress(AlertVersionUpgradeProgress(data, ver_con))
        print(msg)
        await lpgen.send_test_tg_message(msg)


async def node_version_notification_check_1(lpgen: LpAppFramework, data):
    locs = localizations(lpgen)

    await lpgen.send_test_tg_message('------------------------------------')

    for loc in locs:
        sep()
        # noinspection PyTypeChecker
        msg = loc.notification_text_version_changed(
            AlertVersionChanged(
                data,
                new_versions=[
                    VersionInfo.parse('0.59.1'),
                    VersionInfo.parse('0.60.0'),
                ],
                old_active_ver=None,
                new_active_ver=None
            )
        )
        print(msg)
        await lpgen.send_test_tg_message(msg)

    await lpgen.send_test_tg_message('------------------------------------')

    for loc in locs:
        sep()
        msg = loc.notification_text_version_changed(
            AlertVersionChanged(
                data,
                new_versions=[],
                old_active_ver=VersionInfo.parse('0.59.0'),
                new_active_ver=VersionInfo.parse('0.59.1')
            )
        )
        print(msg)
        await lpgen.send_test_tg_message(msg)

    await lpgen.send_test_tg_message('------------------------------------')

    data: NodeSetChanges = copy(data)
    for n in data.nodes_all:
        if random.uniform(0, 1) > 0.35:
            n.version = '0.59.2'
        if random.uniform(0, 1) > 0.25:
            n.version = '0.60.0'
        if random.uniform(0, 1) > 0.20:
            n.version = '0.60.1'
        if random.uniform(0, 1) > 0.15:
            n.version = '0.60.3'

    for loc in locs:
        sep()
        msg = loc.notification_text_version_changed(
            AlertVersionChanged(
                data,
                new_versions=[],
                old_active_ver=VersionInfo.parse('0.59.1'),
                new_active_ver=VersionInfo.parse('0.59.0')
            )
        )
        print(msg)
        await lpgen.send_test_tg_message(msg)


def toss_nodes(nodes, min_n=3, max_n=9):
    churn_out, churn_in = [], []
    random.shuffle(nodes)
    for n in nodes:
        in_enough = (min_n <= len(churn_in) <= max_n)
        out_enough = (min_n <= len(churn_out) <= max_n)
        if in_enough and out_enough:
            break

        if n.is_active and not out_enough:
            n.status = n.STANDBY
            churn_out.append(n)
        elif n.is_standby and not in_enough:
            n.status = n.ACTIVE
            churn_in.append(n)

    return churn_in, churn_out


async def node_churn_notification_test(lpgen: LpAppFramework, nodes):
    locs = localizations(lpgen)

    churn_in, churn_out = toss_nodes(nodes)
    changes = NodeSetChanges([], [], churn_in, churn_out, nodes, nodes,
                             churn_duration=5578)

    # await lpgen.send_test_tg_message('------------------------------------')
    for loc in locs:
        sep()
        msg = loc.notification_text_node_churn_finish(
            changes
        )
        print(msg)
        # await lpgen.send_test_tg_message(msg)


def make_node(is_active=True):
    n = NodeInfo(
        version='1.101.1',
        bond=random.randint(1, 1000000),
        node_address='thor1' + ''.join(random.choices('0123456789abcdef', k=40)),
    )
    n.status = n.ACTIVE if is_active else n.STANDBY
    return n


async def demo_churn_test(app: LpAppFramework):
    det = NodeChurnDetector(app.deps)

    prev_list = [
        make_node(is_active=random.uniform(0, 1) > 0.5) for _ in range(10)
    ]

    new_list = list(prev_list) + [make_node()]

    changes = det.extract_changes(new_list, prev_list)
    print(changes)


async def demo_churn_pipeline(app: LpAppFramework):
    d = app.deps
    churn_detector = NodeChurnDetector(d)
    d.node_info_fetcher.add_subscriber(churn_detector)

    notifier_nodes = NodeChurnNotifier(d)
    churn_detector.add_subscriber(notifier_nodes)

    # notifier_nodes.add_subscriber(d.alert_presenter)  # not ready yet

    achievements = AchievementsNotifier(d)
    achievements.add_subscriber(d.alert_presenter)

    notifier_version = VersionNotifier(d)
    churn_detector.add_subscriber(notifier_version)

    await d.node_info_fetcher.run()


class NodeFetcherSimulator(BaseFetcher):
    def __init__(self, deps: DepContainer, nodes: List[NodeInfo], sleep_period=5):
        super().__init__(deps, sleep_period)
        self.thor_network: Optional[ThorNetwork] = None
        self.status = 'wait'
        self._i = 0
        self.nodes = nodes

    def set_thor_network(self, thor_network: ThorNetwork, migrating=False):
        self.thor_network = thor_network._replace(vaults_migrating=migrating)
        print(f"Set ThorNetwork is {self.thor_network}")

    def set_migration(self, m):
        self.set_thor_network(self.thor_network, m)

    async def fetch(self):
        nodes = self.nodes
        if self.status == 'wait':
            self._i += 1
            if self._i > 2:
                self._i = 0
                self.status = 'start'
                c_in, c_out = toss_nodes(self.nodes)
                print(f'Churn nodes: {len(c_in) = }, {len(c_out) = }')
                self.set_migration(True)
        elif self.status == 'start':
            self._i += 1
            if self._i > 3:
                self.status = 'done'
                self.set_migration(False)
                self._i = 0
        elif self.status == 'done':
            print('Churn simulation is done. You can stop the process now!')
        else:
            exit(-255)
        self.nodes = nodes
        return nodes


async def demo_churn_simulator(app: LpAppFramework, version=False):
    d = app.deps

    nodes: NetworkNodes = await d.deps.node_cache.get()
    print(f"There are {len(nodes)} nodes")

    await d.broadcaster.broadcast_to_all('---------')

    # simulator
    # node_fetcher_simulator.set_thor_network(d.node_info_fetcher.thor_network)

    # churn_detector
    # node_fetcher_simulator.add_subscriber(churn_detector)

    churn_sim = DbgChurnSimulator(app.deps, trigger_on_tick=2, every_tick=True)

    # notifier module
    notifier_nodes = NodeChurnNotifier(d)
    churn_sim.add_subscriber(notifier_nodes)

    notifier_nodes.add_subscriber(d.alert_presenter)

    # the rest of stuff
    achievements = AchievementsNotifier(d)
    achievements.add_subscriber(d.alert_presenter)

    if version:
        notifier_version = VersionNotifier(d)
        churn_sim.node_churn_detector.add_subscriber(notifier_version)

    # await node_fetcher_simulator.run()
    await churn_sim.run_standalone()


async def demo_once(app: LpAppFramework):
    node_info_fetcher = NodeInfoFetcher(app.deps)
    data = await node_info_fetcher.fetch()
    await node_churn_notification_test(app, data)
    # await node_version_notification_check_1(lpgen, data)
    # await node_version_notification_check_progress(lpgen, data)


class DbgChurnFaker:
    @staticmethod
    def _dbg_test_churn(new_nodes: List[NodeInfo]):
        """
        This is for debug purposes
        """
        import random

        active_nodes = [n for n in new_nodes if n.is_active]
        ready_nodes = [n for n in new_nodes if n.is_standby and n.bond > 10_000]

        n_activate = random.randint(1, min(7, len(ready_nodes)))
        n_off = random.randint(1, min(7, len(active_nodes)))
        nodes_off = random.sample(active_nodes, n_off)
        nodes_on = random.sample(ready_nodes, n_activate)
        for n in nodes_off:
            n.status = NodeInfo.STANDBY
        for n in nodes_on:
            n.status = NodeInfo.ACTIVE

        return new_nodes

    @staticmethod
    def _dbg_node_magic(node):
        # if node.node_address == 'thor15tjtgxq7mz3ljwk0rzw6pvj43tz3xsv9f2wfzp':
        if node.node_address == 'thor15tjtgxq7mz3ljwk0rzw6pvj43tz3xsv9f2wfzp':
            # node.status = node.STANDBY
            node.version = '1.88.5'
            ...
            # node.ip_address = f'127.0.0.{random.randint(1, 255)}'
            # node.bond = 100000 + random.randint(0, 1000000)
            print('dyatel', node.node_address, node.bond)
        return node

    def make_some_changes(self, nodes, magic=True, churn=True):
        if magic:
            nodes = [self._dbg_node_magic(n) for n in nodes]

        nodes.sort(key=lambda k: (k.status, -k.bond))

        if churn:
            nodes = self._dbg_test_churn(nodes)
        return nodes

    @staticmethod
    def dbg_modification_of_node_set(data: NodeSetChanges) -> NodeSetChanges:
        # 1. new version
        # for i in range(1, 55):
        #     data.nodes_all[i].version = '1.90.1'
        # data.nodes_all[1].version = '0.88.5'

        # 2. Min versions
        # for n in data.nodes_all:
        #     if random.uniform(0, 1) > 0.5:
        #         n.version = '0.57.5'
        #     n.version = '0.61.66'
        # data.nodes_all[0].version = '0.61.63'

        # 3. Upgrade
        # progress = 0.99  # 0..1
        # for n in data.nodes_all:
        #     if random.uniform(0, 1) <= progress:
        #         n.version = '0.60.6'

        # data.nodes_added.append(data.nodes_all[0])

        # simulate churn
        data.nodes_activated.append(data.nodes_all[1])
        data.nodes_activated.append(data.nodes_all[2])
        data.nodes_activated.append(data.nodes_all[3])
        data.nodes_deactivated.append(data.nodes_all[4])
        data.nodes_deactivated.append(data.nodes_all[5])
        data.nodes_deactivated.append(data.nodes_all[6])
        data.nodes_deactivated.append(data.nodes_all[7])
        data.nodes_deactivated.append(data.nodes_all[8])
        data.nodes_removed.append(data.nodes_all[9])

        return data


async def dbg_node_info_bond_provider_parsing(app: LpAppFramework):
    nodes = await app.deps.node_info_fetcher.fetch()
    for node in nodes:
        node: NodeInfo
        award = node.current_award
        calc_award = sum(bp.anticipated_award for bp in node.bond_providers)
        delta = abs(award - calc_award)
        # verify the bond providers reward sum up to the node reward
        if delta > 0.0001:
            print(f'{node.node_address = }')
            print(f'{award = }')
            print(f'{calc_award = }')
            print(f'{delta = }')
            print('---')

    node_db = NodeStateDatabase(app.deps, key='NodeInfo:_debugNodes')
    await node_db.save_node_info_list(nodes)

    loaded_nodes = await node_db.get_last_node_info_list()
    assert loaded_nodes == nodes

    await most_frequent_addy(nodes)


async def most_frequent_addy(nodes: List[NodeInfo]):
    c = Counter()
    for n in nodes:
        c[n.node_operator] += 1
        for bp in n.bond_providers:
            c[bp.address] += 1

    # format nicely top 10
    print('Top 10 most frequent addresses:')
    for i, (k, v) in enumerate(c.most_common(10), start=1):
        print(f'{i}. {k} -> {v}')


async def main():
    app = LpAppFramework()
    async with app:
        # await demo_churn_pipeline(app)
        # await demo_churn_test(app)
        # await demo_churn_simulator(app)
        # await dbg_node_info_bond_provider_parsing(app)
        await demo_once(app)


if __name__ == "__main__":
    asyncio.run(main())
