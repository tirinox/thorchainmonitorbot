import asyncio
import logging

from lib.texts import sep
from tools.lib.lp_common import LpAppFramework


async def main():
    # print(try_to_decompose_mimir_name('MAXNODETOCHURNOUTSUCKFORLOWVERSIONGGG'))

    lp_app = LpAppFramework(log_level=logging.INFO)
    async with lp_app(brief=True):
        await lp_app.deps.mimir_const_fetcher.run_once()

        rules = lp_app.deps.mimir_const_holder.mimir_rules

        current_names = set([k.upper() for k in lp_app.deps.mimir_const_holder.all_names])
        sep()
        code_gen = ''
        for name in sorted(current_names):
            pretty_name = rules.name_to_human(name)
            code_gen += f'    {name.upper()}: {pretty_name!r},\n'

        print(code_gen)


if __name__ == '__main__':
    asyncio.run(main())
