from random import random
from typing import Optional

from api.midgard.parser import get_parser_by_network_id
from jobs.fetch.base import BaseFetcher
from jobs.fetch.cached.pool import PoolCache
from lib.config import Config
from lib.depcont import DepContainer
from models.pool_info import PoolInfoMap
from models.price import PriceHolder


class PoolFetcher(BaseFetcher):
    """
    This class queries Midgard and THORNodes to get current and historical pool prices and depths
    """

    def __init__(self, deps: DepContainer):
        assert deps
        cfg: Config = deps.cfg
        period = cfg.as_interval('price.pool_fetch_period', '1m')

        super().__init__(deps, sleep_period=period)

        self.deps = deps
        self.cache = PoolCache(deps)

    async def fetch(self) -> PriceHolder:
        current_pools = await self.cache.get()
        return current_pools


class PoolInfoFetcherMidgard(BaseFetcher):
    def __init__(self, deps: DepContainer, period):
        super().__init__(deps, sleep_period=period)
        self.deps = deps
        self.parser = get_parser_by_network_id(self.deps.cfg.network_id)
        self.last_raw_result = None

    async def get_pool_info_midgard(self, period='30d') -> Optional[PoolInfoMap]:
        pool_data = await self.deps.midgard_connector.query_pools(period, parse=False)
        if not pool_data:
            return None
        self.last_raw_result = pool_data
        return self.parser.parse_pool_info(pool_data)

    async def fetch(self):
        result = await self.get_pool_info_midgard()
        return result

    @staticmethod
    def _dbg_test_drop_one(pool_info_map: PoolInfoMap) -> PoolInfoMap:
        if not pool_info_map or random() > 0.5:
            return pool_info_map

        pool_info_map = pool_info_map.copy()
        first_key = next(iter(pool_info_map.keys()))
        del pool_info_map[first_key]
        return pool_info_map
