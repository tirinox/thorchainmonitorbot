import asyncio
import logging

from lib.texts import sep
from models.mimir_naming import MIMIR_DICT_FILENAME
from tools.lib.lp_common import LpAppFramework


async def main():
    lp_app = LpAppFramework(log_level=logging.INFO)
    async with lp_app:

        mimir = await lp_app.deps.mimir_cache.get_mimir_holder()

        mimir.mimir_rules.load(MIMIR_DICT_FILENAME)

        # pools = await lp_app.deps.pool_cache.get_pools()
        # mimir.mimir_rules.update_asset_names(pools)

        converter = mimir.mimir_rules.name_to_human

        current_names = set([k.upper() for k in mimir.all_names_including_voting])

        sep()
        code_gen = ''

        for name in sorted(current_names):
            pretty_name = converter(name)
            code_gen += f'    {name.upper()}: {pretty_name!r},\n'

        print(code_gen)


if __name__ == '__main__':
    asyncio.run(main())
