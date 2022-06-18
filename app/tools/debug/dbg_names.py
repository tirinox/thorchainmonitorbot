import asyncio
import logging

from tools.lib.lp_common import LpAppFramework


async def t_names1(lp_app: LpAppFramework):
    ns = lp_app.deps.name_service
    n = await ns.lookup_name('thor17gw75axcnr8747pkanye45pnrwk7p9c3cqncsv')
    print(n)

    n = await ns.lookup_name('thorNONAME')
    assert n is None


async def main():
    lp_app = LpAppFramework(log_level=logging.INFO)
    async with lp_app(brief=True):
        await t_names1(lp_app)


if __name__ == '__main__':
    asyncio.run(main())
