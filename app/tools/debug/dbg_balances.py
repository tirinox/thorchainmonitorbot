# balances and synths
import asyncio
import logging
import os

from lib.texts import sep
from tools.lib.lp_common import LpAppFramework


async def main():
    lp_app = LpAppFramework(log_level=logging.INFO)
    async with lp_app:
        
        address = os.environ.get('EXAMPLE_ADDRESS')
        if not address:
            raise ValueError('EXAMPLE_ADDRESS env variable is not set')

        balances = await lp_app.deps.trade_acc_fetcher.get_whole_balances(address, with_trade_account=True)

        loc = lp_app.deps.loc_man.default

        sep()
        ph = await lp_app.deps.pool_cache.get()
        text = loc.text_balances(balances, 'Balances', ph)
        print(text)
        sep()
        await lp_app.send_test_tg_message(text)

        nodes = await lp_app.deps.node_cache.get()

        bond_and_nodes = list(nodes.find_bond_providers(address))
        # bonds = [bp for _, bp in bond_and_nodes]

        sep()
        usd_per_rune = ph.usd_per_rune
        text = loc.text_bond_provision(bond_and_nodes, usd_per_rune=usd_per_rune)
        print(text)
        sep()
        await lp_app.send_test_tg_message(text)


if __name__ == '__main__':
    asyncio.run(main())
