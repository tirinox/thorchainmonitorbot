import asyncio
import logging

from tools.lib.lp_common import LpAppFramework


async def t_names1(lp_app: LpAppFramework):
    ns = lp_app.deps.name_service
    n = await ns.lookup_name_by_address('thor17gw75axcnr8747pkanye45pnrwk7p9c3cqncsv')
    print(n)

    n = await ns.lookup_name_by_address('thorNONAME')
    assert n is None

    n = await ns.lookup_address_by_name('Binance Hot')
    assert n.startswith('thor')
    print(n)


async def main():
    lp_app = LpAppFramework(log_level=logging.INFO)
    async with lp_app(brief=True):
        await t_names1(lp_app)


if __name__ == '__main__':
    asyncio.run(main())
