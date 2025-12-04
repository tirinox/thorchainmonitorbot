import asyncio
import logging
import random

from api.midgard.name_service import NameMap
from comm.localization.languages import Language
from comm.telegram.telegram import TG_TEST_USER
from jobs.fetch.node_info import NodeInfoFetcher
from jobs.node_churn import NodeChurnDetector
from lib.date_utils import now_ts, DAY
from lib.texts import sep
from models.node_info import NodeEvent, NodeEventType, EventProviderStatus, EventNodeFeeChange, \
    EventProviderBondChange, NetworkNodes
from notify.personal.bond_provider import PersonalBondProviderNotifier
from tools.debug.dbg_record_nodes import NodesDBRecorder, NodePlayer
from tools.lib.churn_sim import DbgChurnSimulator
from tools.lib.lp_common import LpAppFramework


async def demo_run_churn_sim_continuously(app: LpAppFramework):
    d = app.deps

    churn_sim = DbgChurnSimulator(d, trigger_on_tick=2, every_tick=True, tick_duration=3)

    bond_provider_tools = PersonalBondProviderNotifier(d)
    churn_sim.add_subscriber(bond_provider_tools)

    await churn_sim.run_standalone()


async def demo_all_kinds_of_messages(app: LpAppFramework):
    nodes: NetworkNodes = await app.deps.node_cache.get()

    node = next(n for n in nodes.node_info_list if n.is_active and n.bond_providers)
    bond_provider = random.choice(node.bond_providers)
    bp_address = bond_provider.address

    sep()
    print(f'{node = }')
    print(f'{bond_provider = }')
    sep()

    events = [
        NodeEvent.new(node, NodeEventType.PRESENCE,
                      EventProviderStatus(bp_address, bond_provider.rune_bond, appeared=False)),
        NodeEvent.new(node, NodeEventType.PRESENCE,
                      EventProviderStatus(bp_address, bond_provider.rune_bond, appeared=True)),
        NodeEvent.new(node, NodeEventType.FEE_CHANGE, EventNodeFeeChange(bp_address, 0.1, 0.2)),
        NodeEvent.new(node, NodeEventType.FEE_CHANGE, EventNodeFeeChange(bp_address, 0.2, 0.133)),

        NodeEvent.new(node, NodeEventType.CHURNING,
                      EventProviderStatus(bp_address, bond_provider.rune_bond, appeared=True)),
        NodeEvent.new(node, NodeEventType.CHURNING,
                      EventProviderStatus(bp_address, bond_provider.rune_bond, appeared=False,
                                          previous_ts=now_ts() - 12888)),

        NodeEvent.new(node, NodeEventType.BOND_CHANGE,
                      EventProviderBondChange(bp_address, bond_provider.rune_bond, bond_provider.rune_bond *
                                              random.uniform(1.0, 1.007), on_churn=True,
                                              duration_sec=3 * DAY)),
        NodeEvent.new(node, NodeEventType.BOND_CHANGE,
                      EventProviderBondChange(bp_address, bond_provider.rune_bond, bond_provider.rune_bond *
                                              random.uniform(0.997, 1.0), on_churn=True,
                                              duration_sec=5 * DAY)),
        NodeEvent.new(node, NodeEventType.BOND_CHANGE,
                      EventProviderBondChange(bp_address, bond_provider.rune_bond, bond_provider.rune_bond *
                                              random.uniform(1.01, 1.5), on_churn=False)),
        NodeEvent.new(node, NodeEventType.BOND_CHANGE,
                      EventProviderBondChange(bp_address, bond_provider.rune_bond, bond_provider.rune_bond *
                                              random.uniform(0.5, 0.99), on_churn=False)),

        NodeEvent.new(node, NodeEventType.BOND_CHANGE,
                      EventProviderBondChange(bp_address, 0, 1, on_churn=False)),
        NodeEvent.new(node, NodeEventType.BOND_CHANGE,
                      EventProviderBondChange(bp_address, 100, 0, on_churn=False, duration_sec=3 * DAY)),

        NodeEvent.new(node, NodeEventType.BP_PRESENCE,
                      EventProviderStatus(bp_address, bond_provider.rune_bond, appeared=True,
                                          previous_ts=now_ts() - 1234)),
        NodeEvent.new(node, NodeEventType.BP_PRESENCE,
                      EventProviderStatus(bp_address, bond_provider.rune_bond, appeared=False)),

    ]

    name_map = NameMap.empty()

    bond_provider_tools = PersonalBondProviderNotifier(app.deps)

    # loc: BaseLocalization = app.deps.loc_man.get_from_lang(Language.RUSSIAN)
    locs = [app.deps.loc_man.get_from_lang(Language.RUSSIAN), app.deps.loc_man.default]

    for loc in locs:
        aggregate_text = await bond_provider_tools.generate_message_text(loc, events, None, None, None, name_map)
        print(aggregate_text)
        sep()
        await app.send_test_tg_message(aggregate_text)


DEFAULTS_FILE_NAME_FOR_DB_BIG = f'../temp/mainnet_nodes_db_1.json'
DEFAULTS_FILE_NAME_FOR_DB_SMALL = f'../temp/mainnet_nodes_db_small.json'


async def run_recorder(app: LpAppFramework, start, end, file=None):
    recorder = NodesDBRecorder(app, filename=file or DEFAULTS_FILE_NAME_FOR_DB_BIG)

    await recorder.load_db()
    recorder.print_db_map()

    # await recorder.diff(12602377, 12602978)

    await recorder.ensure_last_block()

    await recorder.scan(start, end)
    await recorder.save_db()


async def run_playback(app: LpAppFramework, file=None, delay=5.0):
    recorder = NodesDBRecorder(app, filename=file or DEFAULTS_FILE_NAME_FOR_DB_BIG)
    await recorder.load_db()
    recorder.print_db_map()

    player = NodePlayer(recorder.db)

    churn_detector = NodeChurnDetector(app.deps)

    bond_provider_tools = PersonalBondProviderNotifier(app.deps)
    bond_provider_tools.log_events = True
    churn_detector.add_subscriber(bond_provider_tools)

    for block, nodes in player:
        sep(f'#{block}')
        # noinspection PyTypeChecker
        await churn_detector.on_data(None, nodes)
        await asyncio.sleep(delay)


async def run_realtime(app: LpAppFramework):
    d = app.deps

    churn_detector = NodeChurnDetector(app.deps)

    d.node_info_fetcher = NodeInfoFetcher(d)
    d.node_info_fetcher.add_subscriber(churn_detector)

    bond_provider_tools = PersonalBondProviderNotifier(app.deps)
    bond_provider_tools.log_events = True

    churn_detector.add_subscriber(bond_provider_tools)

    await app.deps.node_info_fetcher.run()


async def analise_churn(app: LpAppFramework):
    recorder = NodesDBRecorder(app, filename=DEFAULTS_FILE_NAME_FOR_DB_SMALL)
    await recorder.load_db()

    # Churn example: 12606980 .. 12606982
    # Churn example: 12990302 .. 12991502
    changes = await recorder.diff_node_set_changes(12985895 - 5, 12985895 + 5)
    await recorder.save_db()

    bond_provider_tools = PersonalBondProviderNotifier(app.deps)
    # bond_provider_tools.log_events = True

    await bond_provider_tools.watcher.add_user_to_node(TG_TEST_USER, 'thor1nfzkz5qcq46edmgn4kus8a2m4rqhm69dkktw48')

    # this guy out
    await bond_provider_tools.watcher.add_user_to_node(TG_TEST_USER, 'thor1un5fznfjnx3slzv6pgmhd7x898n9jz7ce8ng82')

    # this guy in
    await bond_provider_tools.watcher.add_user_to_node(TG_TEST_USER, 'thor1tcet6mxe80x89a8dlpynehlj4ya7cae4v3hmce')

    await bond_provider_tools.watcher.add_user_to_node(TG_TEST_USER, 'thor1yyfmkh6yd0tytk7nh7htq3fw27xsfk3x8wnr0j')
    await bond_provider_tools.watcher.add_user_to_node(TG_TEST_USER, 'thor1nmnq0r99fwfkp3pg8sdj4wlj2l96hx73m6835y')
    await bond_provider_tools.watcher.add_user_to_node(TG_TEST_USER, 'thor13tqs4dgvjyhukx2aed78lu6gz49t6penjwnd50')

    await bond_provider_tools.on_data(None, changes)

    await asyncio.sleep(5.0)


async def debug_fee_change(app: LpAppFramework):
    recorder = NodesDBRecorder(app, filename=DEFAULTS_FILE_NAME_FOR_DB_SMALL)
    await recorder.load_db()

    changes = await recorder.diff_node_set_changes(12400980, 12606982)
    await recorder.save_db()

    bond_provider_tools = PersonalBondProviderNotifier(app.deps)

    await bond_provider_tools.watcher.add_user_to_node(TG_TEST_USER, 'thor1nfzkz5qcq46edmgn4kus8a2m4rqhm69dkktw48')
    await bond_provider_tools.watcher.add_user_to_node(TG_TEST_USER, 'thor1yyfmkh6yd0tytk7nh7htq3fw27xsfk3x8wnr0j')

    await bond_provider_tools.on_data(None, changes)

    # fee_events = list(bond_provider_tools._extract_fee_changes(changes))
    # print(fee_events)


async def main():
    app = LpAppFramework(log_level=logging.INFO)
    async with app:
        app.deps.thor_connector.env.timeout = 100
        # await demo_run_churn_sim_continuously(app)
        # await run_realtime(app)
        # await run_playback(app, delay=0.01)
        # await debug_fee_change(app)
        # await demo_all_kinds_of_messages(app)
        # await analise_churn(app)
        # await dbg_second_chance_before_deactivating_channel(app)

        # await run_recorder(app, 18298005 - 3, 18298005 + 3, file='../temp/whitelist1.json')
        await run_playback(app, file='../temp/whitelist1.json', delay=1)


if __name__ == '__main__':
    asyncio.run(main())
