import asyncio

from services.dialog.picture.pools_picture import PoolPictureGenerator
from services.jobs.fetch.pool_price import PoolInfoFetcherMidgard
from services.models.pool_info import PoolMapPair, PoolInfoMap
from tools.lib.lp_common import LpAppFramework, save_and_show_pic


async def main():
    lp_app = LpAppFramework()
    async with lp_app(brief=True):
        # pools: PoolInfoMap = await lp_app.deps.pool_fetcher.reload_global_pools()

        mdg = PoolInfoFetcherMidgard(lp_app.deps, 10)
        pools = await mdg.get_pool_info_midgard()

        print(pools)
        loc = lp_app.deps.loc_man.default
        event = PoolMapPair(pools, pools)
        pool_pic_gen = PoolPictureGenerator(loc, event)
        pool_pic, _ = await pool_pic_gen.get_picture()
        save_and_show_pic(pool_pic, 'pools.png')


if __name__ == '__main__':
    asyncio.run(main())
