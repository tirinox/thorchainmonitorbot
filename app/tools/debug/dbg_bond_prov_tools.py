import asyncio
import random

from localization.eng_base import BaseLocalization
from services.jobs.node_churn import NodeChurnDetector
from services.lib.midgard.name_service import NameMap
from services.lib.texts import sep
from services.models.node_info import NodeEvent, NodeEventType, EventProviderStatus, EventNodeFeeChange, \
    EventProviderBondChange
from services.notify.personal.bond_provider import PersonalBondProviderNotifier
from tools.lib.lp_common import LpAppFramework


async def demo_run_continuously(app: LpAppFramework):
    d = app.deps

    churn_detector = NodeChurnDetector(d)
    d.node_info_fetcher.add_subscriber(churn_detector)

    bond_provider_tools = PersonalBondProviderNotifier(d)
    churn_detector.add_subscriber(bond_provider_tools)

    await d.node_info_fetcher.run()

async def demo_all_kinds_of_messages(app: LpAppFramework):
    loc: BaseLocalization = app.deps.loc_man.default

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

    aggregate_text = ''
    for event in events:
        text = loc.notification_text_bond_provider_alert(event, name_map)
        aggregate_text += text + '\n\n'
        print(text)
        sep()

    await app.send_test_tg_message(aggregate_text)



async def main():
    app = LpAppFramework()
    async with app():
        # await demo_run_continuously(app)
        await demo_all_kinds_of_messages(app)


if __name__ == '__main__':
    asyncio.run(main())
