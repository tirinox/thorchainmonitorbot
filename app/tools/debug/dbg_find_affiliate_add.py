import asyncio

from services.jobs.affiliate_merge import merge_affiliate_txs
from services.lib.midgard.connector import MidgardConnector
from services.lib.midgard.parser import get_parser_by_network_id
from services.lib.midgard.urlgen import free_url_gen
from services.models.tx import ThorTx
from tools.lib.lp_common import LpAppFramework


async def my_test_midgard1():
    lp_app = LpAppFramework()
    async with lp_app:
        await lp_app.prepare(brief=True)
        mdg: MidgardConnector = lp_app.deps.midgard_connector
        tx_parser = get_parser_by_network_id(lp_app.deps.cfg.network_id)

        txs = []
        for page in range(10):
            q_path = free_url_gen.url_for_tx(page * 50, 50, types='addLiquidity')
            j = await mdg.request_random_midgard(q_path)
            txs += tx_parser.parse_tx_response(j).txs

        txs_merged = merge_affiliate_txs(txs)

        for tx in txs:
            tx: ThorTx
            if tx.affiliate_fee > 0:
                print(f'{tx.affiliate_fee = }, {tx.tx_hash}')

        print(f'{len(txs) = } and {len(txs_merged) = }')


async def main():
    await my_test_midgard1()


if __name__ == '__main__':
    asyncio.run(main())
