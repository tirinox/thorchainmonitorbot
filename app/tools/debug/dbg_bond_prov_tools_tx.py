import asyncio
import logging

from notify.personal.bond_provider import PersonalBondProviderNotifier
from notify.personal.bond_tx_detect import BondTxDetector
from notify.personal.bond_tx_notify import PersonalBondTxNotifier
from tools.lib.lp_common import LpAppFramework


async def demo_bond_tx_scan(app: LpAppFramework):
    d = app.deps
    bond_provider_tools = PersonalBondProviderNotifier(d)
    bond_provider_tools.log_events = d.cfg.get('node_info.bond_tools.log_events')

    if d.block_scanner:
        bond_event_detector = BondTxDetector(d)
        bond_tx_notifier = PersonalBondTxNotifier(d)
        d.block_scanner.add_subscriber(bond_event_detector)
        bond_event_detector.add_subscriber(bond_tx_notifier)

    ...


async def main():
    app = LpAppFramework(log_level=logging.INFO)
    async with app(brief=True):
        app.deps.thor_connector.env.timeout = 100
        await demo_bond_tx_scan(app)


if __name__ == '__main__':
    asyncio.run(main())
