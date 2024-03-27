import asyncio
import random
from copy import deepcopy

from localization.languages import Language
from services.dialog.picture.pools_picture import PoolPictureGenerator
from services.jobs.fetch.pool_price import PoolInfoFetcherMidgard
from services.lib.utils import random_chance
from services.models.pool_info import PoolMapPair, PoolInfoMap
from tools.lib.lp_common import LpAppFramework, save_and_show_pic


async def main():
    lp_app = LpAppFramework()
    async with lp_app(brief=True):
        # pools: PoolInfoMap = await lp_app.deps.pool_fetcher.reload_global_pools()

        mdg = PoolInfoFetcherMidgard(lp_app.deps, 10)
        pools = await mdg.get_pool_info_midgard()

        prev_pools = deepcopy(pools)
        if randomize := True:
            for k, v in prev_pools.items():
                if random_chance(80):
                    v.pool_apr *= random.uniform(0.5, 1.5)
                if random_chance(80):
                    v.balance_asset *= random.uniform(0.5, 1.5)
                if random_chance(80):
                    v.balance_rune *= random.uniform(0.5, 1.5)
                if random_chance(80):
                    v.volume_24h *= random.uniform(0.5, 1.5)

        print(pools)
        # loc = lp_app.deps.loc_man.default
        loc = lp_app.deps.loc_man[Language.RUSSIAN]
        event = PoolMapPair(pools, prev_pools)
        pool_pic_gen = PoolPictureGenerator(loc, event)
        pool_pic, _ = await pool_pic_gen.get_picture()
        save_and_show_pic(pool_pic, 'pools.png')


if __name__ == '__main__':
    asyncio.run(main())
