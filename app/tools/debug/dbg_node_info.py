import asyncio
import logging
import random
from copy import copy

from semver import VersionInfo

from localization.languages import Language
from localization.manager import LocalizationManager
from services.jobs.achievement.notifier import AchievementsNotifier
from services.jobs.fetch.node_info import NodeInfoFetcher
from services.jobs.node_churn import NodeChurnDetector
from services.lib.texts import sep
from services.lib.utils import setup_logs
from services.models.node_info import NodeSetChanges, NodeVersionConsensus, NodeInfo
from services.notify.types.node_churn_notify import NodeChurnNotifier
from services.notify.types.version_notify import VersionNotifier
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
        msg = loc.notification_text_version_upgrade_progress(data, ver_con)
        print(msg)
        await lpgen.send_test_tg_message(msg)


async def node_version_notification_check_1(lpgen: LpAppFramework, data):
    locs = localizations(lpgen)

    await lpgen.send_test_tg_message('------------------------------------')

    for loc in locs:
        sep()
        msg = loc.notification_text_version_upgrade(
            data,
            new_versions=[
                VersionInfo.parse('0.59.1'),
                VersionInfo.parse('0.60.0'),
            ],
            old_active_ver=None,
            new_active_ver=None
        )
        print(msg)
        await lpgen.send_test_tg_message(msg)

    await lpgen.send_test_tg_message('------------------------------------')

    for loc in locs:
        sep()
        msg = loc.notification_text_version_upgrade(
            data,
            new_versions=[],
            old_active_ver=VersionInfo.parse('0.59.0'),
            new_active_ver=VersionInfo.parse('0.59.1')
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
        msg = loc.notification_text_version_upgrade(
            data,
            new_versions=[],
            old_active_ver=VersionInfo.parse('0.59.1'),
            new_active_ver=VersionInfo.parse('0.59.0')
        )
        print(msg)
        await lpgen.send_test_tg_message(msg)


async def node_churn_notification_test(lpgen: LpAppFramework, nodes):
    locs = localizations(lpgen)

    random.shuffle(nodes)

    churn_out, churn_in = [], []
    for n in nodes:
        in_enough = (4 <= len(churn_in) <= 8)
        out_enough = (4 <= len(churn_out) <= 8)
        if in_enough and out_enough:
            break

        if n.is_active and not out_enough:
            n.status = n.STANDBY
            churn_out.append(n)
        elif n.is_standby and not in_enough:
            n.status = n.ACTIVE
            churn_in.append(n)

    changes = NodeSetChanges([], [], churn_in, churn_out, nodes, nodes)

    # await lpgen.send_test_tg_message('------------------------------------')
    for loc in locs:
        sep()
        msg = loc.notification_text_for_node_churn(
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


async def demo_once(app: LpAppFramework):
    node_info_fetcher = NodeInfoFetcher(app.deps)
    data = await node_info_fetcher.fetch()
    await node_churn_notification_test(app, data)
    # await node_version_notification_check_1(lpgen, data)
    # await node_version_notification_check_progress(lpgen, data)


async def main():
    app = LpAppFramework()
    async with app:
        await demo_churn_pipeline(app)
        # await demo_churn_test(app)


if __name__ == "__main__":
    setup_logs(logging.INFO)
    asyncio.run(main())
