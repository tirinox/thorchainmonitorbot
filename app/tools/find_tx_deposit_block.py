"""
This script is used to find the block where the tx was observed.
"""

import asyncio
import os

from jobs.scanner.native_scan import BlockScanner
from jobs.scanner.tx import ThorObservedTx
from lib.texts import sep
from lib.utils import say
from tools.lib.lp_common import LpAppFramework


def is_our_tx(tx: ThorObservedTx, tx_id_to_find):
    if tx.tx_id.lower() == tx_id_to_find:
        return True


async def run():
    app = LpAppFramework()
    async with app:
        tx_id = os.environ.get("TXID") or input("Enter tx_id: ")
        tx_id = tx_id.lower().strip()
        print("Tx id:", tx_id)
        print("I am looking for a block with this tx finalised in...")

        sep()
        tx = await app.deps.thor_connector.query_tx_simple(tx_id)
        if not tx:
            print("Tx not found")
            return

        height = tx['finalised_height']

        print("Finalised height is ", height)
        sep()

        height -= 1

        scanner = BlockScanner(app.deps)

        finished = False
        while height > 0 and not finished:
            block = await scanner.fetch_one_block(height)

            for tx in block.all_observed_txs:
                if is_our_tx(tx, tx_id):
                    sep()
                    print(f"Found it! block height: {height}")
                    print(f"https://runescan.io/block/{height}")
                    print(f"https://runescan.io/tx/{tx_id}")
                    await say("found!")
                    finished = True
                    break

            height -= 1


if __name__ == '__main__':
    asyncio.run(run())
