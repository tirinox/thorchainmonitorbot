import asyncio
import logging
import random

from localization.eng_base import BaseLocalization
from localization.languages import Language
from services.dialog.telegram.telegram import TG_TEST_USER
from services.jobs.node_churn import NodeChurnDetector
from services.lib.midgard.name_service import NameMap
from services.lib.texts import sep
from services.models.node_info import NodeEvent, NodeEventType, EventProviderStatus, EventNodeFeeChange, \
    EventProviderBondChange
from services.notify.personal.bond_provider import PersonalBondProviderNotifier
from tools.debug.dbg_record_nodes import NodesDBRecorder, NodePlayer
from tools.lib.lp_common import LpAppFramework


async def demo_run_continuously(app: LpAppFramework):
    d = app.deps

    churn_detector = NodeChurnDetector(d)
    d.node_info_fetcher.add_subscriber(churn_detector)

    bond_provider_tools = PersonalBondProviderNotifier(d)
    churn_detector.add_subscriber(bond_provider_tools)

    await d.node_info_fetcher.run()


async def demo_all_kinds_of_messages(app: LpAppFramework):
    await app.deps.node_info_fetcher.run_once()

    node = next(n for n in app.deps.node_holder.nodes if n.is_active and n.bond_providers)
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
                      EventProviderStatus(bp_address, bond_provider.rune_bond, appeared=False)),

        NodeEvent.new(node, NodeEventType.BOND_CHANGE,
                      EventProviderBondChange(bp_address, bond_provider.rune_bond, bond_provider.rune_bond *
                                              random.uniform(1.01, 1.5), on_churn=True)),
        NodeEvent.new(node, NodeEventType.BOND_CHANGE,
                      EventProviderBondChange(bp_address, bond_provider.rune_bond, bond_provider.rune_bond *
                                              random.uniform(0.5, 0.99), on_churn=True)),
        NodeEvent.new(node, NodeEventType.BOND_CHANGE,
                      EventProviderBondChange(bp_address, bond_provider.rune_bond, bond_provider.rune_bond *
                                              random.uniform(1.01, 1.5), on_churn=False)),
        NodeEvent.new(node, NodeEventType.BOND_CHANGE,
                      EventProviderBondChange(bp_address, bond_provider.rune_bond, bond_provider.rune_bond *
                                              random.uniform(0.5, 0.99), on_churn=False)),

        NodeEvent.new(node, NodeEventType.BP_PRESENCE,
                      EventProviderStatus(bp_address, bond_provider.rune_bond, appeared=True)),
        NodeEvent.new(node, NodeEventType.BP_PRESENCE,
                      EventProviderStatus(bp_address, bond_provider.rune_bond, appeared=False)),
    ]

    name_map = NameMap({}, {})

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


async def run_recorder(app: LpAppFramework):
    recorder = NodesDBRecorder(app, filename=DEFAULTS_FILE_NAME_FOR_DB_BIG)

    await recorder.load_db()
    recorder.print_db_map()

    # await recorder.diff(12602377, 12602978)

    await recorder.ensure_last_block()

    start = 12529212 - 20
    await recorder.scan(left_block=start, right_block=12603435)
    await recorder.save_db()


async def run_playback(app: LpAppFramework, delay=5.0):
    recorder = NodesDBRecorder(app, filename=DEFAULTS_FILE_NAME_FOR_DB_BIG)
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


async def analise_churn(app: LpAppFramework):
    recorder = NodesDBRecorder(app, filename=DEFAULTS_FILE_NAME_FOR_DB_SMALL)
    await recorder.load_db()

    # Churn example: 12606980 .. 12606982
    changes = await recorder.diff_node_set_changes(12606980, 12606982)
    await recorder.save_db()

    bond_provider_tools = PersonalBondProviderNotifier(app.deps)
    # bond_provider_tools.log_events = True

    await bond_provider_tools.watcher.add_user_to_node(TG_TEST_USER, 'thor1nfzkz5qcq46edmgn4kus8a2m4rqhm69dkktw48')

    # this guy out
    await bond_provider_tools.watcher.add_user_to_node(TG_TEST_USER, 'thor1un5fznfjnx3slzv6pgmhd7x898n9jz7ce8ng82')

    # this guy in
    await bond_provider_tools.watcher.add_user_to_node(TG_TEST_USER, 'thor1tcet6mxe80x89a8dlpynehlj4ya7cae4v3hmce')



    await bond_provider_tools.on_data(None, changes)

    await asyncio.sleep(5.0)


async def debug_fee_change(app: LpAppFramework):
    recorder = NodesDBRecorder(app, filename=DEFAULTS_FILE_NAME_FOR_DB_SMALL)
    await recorder.load_db()

    changes = await recorder.diff_node_set_changes(12400980, 12606982)
    await recorder.save_db()

    bond_provider_tools = PersonalBondProviderNotifier(app.deps)

    await bond_provider_tools.watcher.add_user_to_node(TG_TEST_USER, 'thor1nfzkz5qcq46edmgn4kus8a2m4rqhm69dkktw48')

    await bond_provider_tools.on_data(None, changes)

    # fee_events = list(bond_provider_tools._extract_fee_changes(changes))
    # print(fee_events)



async def main():
    app = LpAppFramework(log_level=logging.INFO)
    async with app(brief=True):
        app.deps.thor_env.timeout = 100
        # await demo_run_continuously(app)

        # await run_playback(app, delay=0.01)

        # await debug_fee_change(app)

        await demo_all_kinds_of_messages(app)
        # await analise_churn(app)


if __name__ == '__main__':
    asyncio.run(main())
