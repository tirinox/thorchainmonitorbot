import asyncio
import logging

from jobs.runeyield.borrower import BorrowerPositionGenerator
from api.midgard.connector import MidgardConnector
from tools.lib.lp_common import LpAppFramework


async def demo_analise_borrower_pools(lp_app):
    mdg: MidgardConnector = lp_app.deps.midgard_connector
    borrowers = await mdg.request('/v2/borrowers')
    print(f"Total borrowers: {len(borrowers)}")

    bpg = BorrowerPositionGenerator(lp_app.deps)

    for borrower in borrowers:
        positions = await bpg.get_borrower_positions_midgard(borrower)
        for position in positions:
            if len(position.target_assets) > 1:
                print(f'?? {borrower} => {position.target_assets}')
                print('----')
        print('.', end='')


async def main():
    lp_app = LpAppFramework(log_level=logging.INFO)
    async with lp_app():
        await demo_analise_borrower_pools(lp_app)


if __name__ == '__main__':
    asyncio.run(main())
