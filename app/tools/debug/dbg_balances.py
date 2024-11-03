# balances and synths
import asyncio
import logging
import os

from comm.localization.manager import BaseLocalization
from lib.texts import sep
from models.node_info import NodeListHolder
from tools.lib.lp_common import LpAppFramework


async def main():
    lp_app = LpAppFramework(log_level=logging.INFO)
    async with lp_app:
        await lp_app.prepare(brief=True)
        address = os.environ.get('EXAMPLE_ADDRESS')
        if not address:
            raise ValueError('EXAMPLE_ADDRESS env variable is not set')

        balances = await lp_app.deps.trade_acc_fetcher.get_whole_balances(address, with_trade_account=True)

        sep()
        text = BaseLocalization.text_balances(balances)
        print(text)
        sep()

        bond_and_nodes = list(lp_app.deps.node_holder.find_bond_providers(address))
        # bonds = [bp for _, bp in bond_and_nodes]

        sep()
        usd_per_rune = lp_app.deps.price_holder.usd_per_rune
        text = lp_app.deps.loc_man.default.text_bond_provision(bond_and_nodes, usd_per_rune=usd_per_rune)
        print(text)
        sep()
        await lp_app.send_test_tg_message(text)


if __name__ == '__main__':
    asyncio.run(main())
