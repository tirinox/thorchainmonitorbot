from jobs.fetch.pool_price import PoolInfoFetcherMidgard
from lib.cache import async_cache
from lib.date_utils import HOUR
from lib.depcont import DepContainer
from lib.logs import WithLogger
from lib.prev_state import PrevStateDB
from models.pool_info import EventPools, PoolMapStruct
from models.price import PriceHolder


class BestPoolsFetcher(WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.pvdb = PrevStateDB(self.deps.db, PoolMapStruct)

    async def save_prev_pool_map(self, pool_map_struct: PoolMapStruct):
        await self.pvdb.set(pool_map_struct)

    async def get_top_pools(self, income_intervals=7, income_period='day'):
        earnings = await self.deps.midgard_connector.query_earnings(count=income_intervals * 2 + 1,
                                                                    interval=income_period)

        mdg_pool_fetcher = PoolInfoFetcherMidgard(self.deps, 1.0)
        pool_map_struct = await mdg_pool_fetcher.fetch_as_pool_map_struct()
        if not pool_map_struct or not pool_map_struct.pool_map:
            raise ValueError("No pools loaded!")

        usd_per_rune = PriceHolder(self.deps.cfg.stable_coins).calculate_rune_price_here(pool_map_struct.pool_map)
        if not usd_per_rune:
            raise ValueError("Rune price is not available!")

        prev_pool_map = await self.pvdb.get()

        event_pools = EventPools(
            pool_map_struct.pool_map, prev_pool_map.pool_map,
            earnings,
            usd_per_rune=usd_per_rune
        )
        return event_pools, pool_map_struct

    @async_cache(ttl=HOUR)
    async def get_top_pools_cached(self, income_intervals=7, income_period='day'):
        return await self.get_top_pools(income_intervals, income_period)
