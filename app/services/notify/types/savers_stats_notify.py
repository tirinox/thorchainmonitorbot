import asyncio
from itertools import chain
from typing import NamedTuple, List, Dict

from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger
from services.models.pool_info import PoolInfoMap


class AllSavers(NamedTuple):
    total_unique_savers: int
    pool_to_count: Dict[str, int]


class SaversStatsNotifier(WithDelegates, INotified, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

    async def get_one_pool_members(self, asset, height=0):
        return await self.deps.thor_connector.query_savers(asset, height=height)

    async def get_all_savers(self, pool_map: PoolInfoMap):
        active_pools = [p for p in pool_map.values() if p.is_enabled and p.savers_units > 0]
        per_pool_members = await asyncio.gather(
            *(self.get_one_pool_members(p.asset) for p in active_pools)
        )
        return AllSavers(
            total_unique_savers=len(set(chain(*per_pool_members))),
            pool_to_count={pool.asset: len(members) for pool, members in zip(active_pools, per_pool_members)}
        )

    async def on_data(self, sender, pools: PoolInfoMap):
        pass
