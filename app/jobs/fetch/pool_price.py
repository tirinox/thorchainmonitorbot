import json
from contextlib import suppress
from random import random
from typing import Optional, List, Dict

from redis.asyncio import Redis
from ujson import JSONDecodeError

from api.midgard.parser import get_parser_by_network_id
from jobs.fetch.base import BaseFetcher
from jobs.price_recorder import PriceRecorder
from lib.config import Config
from lib.constants import THOR_BLOCK_TIME
from lib.date_utils import parse_timespan_to_seconds, DAY
from lib.depcont import DepContainer
from lib.logs import WithLogger
from models.pool_info import parse_thor_pools, PoolInfo, PoolInfoMap


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
        self.parser = get_parser_by_network_id(self.deps.cfg.network_id)
        self.cache = PoolCache(deps)

    async def fetch(self) -> PoolInfoMap:
        current_pools = await self.load_pools()

        # sometimes clear the cache
        await self.cache.automatic_clear()

        return current_pools

    async def load_pools(self, height=None, caching=True) -> PoolInfoMap:
        if caching:
            if height is None:
                # latest
                pool_map = await self._fetch_current_pool_data_from_thornode()
                cache_key = self.deps.last_block_store.thor
                await self.cache.put(cache_key, pool_map)
            else:
                pool_map = await self.cache.get(height)
                if not pool_map:
                    pool_map = await self._fetch_current_pool_data_from_thornode(height)
                    await self.cache.put(height, pool_map)
        else:
            pool_map = await self._fetch_current_pool_data_from_thornode(height)
        return pool_map

    async def _fetch_current_pool_data_from_thornode(self, height=None) -> PoolInfoMap:
        try:
            thor_pools = await self.deps.thor_connector.query_pools(height)

            # in case of empty response, try to load from the archive
            if not thor_pools:
                thor_pools = await self.deps.thor_connector_archive.query_pools(height)

            return parse_thor_pools(thor_pools)
        except (TypeError, IndexError, JSONDecodeError) as e:
            self.logger.error(f'thor_connector.query_pools failed! Err: {e} at {height = }')

        return {}

    @staticmethod
    def convert_pool_list_to_dict(pool_list: List[PoolInfo]) -> Dict[str, PoolInfo]:
        return {p.asset: p for p in pool_list} if pool_list else None


class PoolInfoFetcherMidgard(BaseFetcher):
    def __init__(self, deps: DepContainer, period):
        super().__init__(deps, sleep_period=period)
        self.deps = deps
        self.parser = get_parser_by_network_id(self.deps.cfg.network_id)
        self.last_raw_result = None

    async def get_pool_info_midgard(self, period='30d') -> Optional[PoolInfoMap]:
        pool_data = await self.deps.midgard_connector.query_pools(period, parse=False)
        if not pool_data:
            return
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


class PoolCache(WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self._pool_cache_saves = 0
        self._pool_cache_clear_every = 1000

        self.pool_cache_max_age = parse_timespan_to_seconds(deps.cfg.price.pool_cache_max_age)
        assert self.pool_cache_max_age > 0

    DB_KEY_POOL_INFO_HASH = 'PoolInfo:hashtable_v2'

    async def clear(self, max_age=1000 * DAY):
        r: Redis = await self.deps.db.get_redis()

        top_block = self.deps.last_block_store.thor
        if top_block is None or top_block < 1:
            self.logger.warning(f'Failed to get top block from the store ({top_block = })')
            return

        min_block = int(max(1, top_block - max_age / THOR_BLOCK_TIME))
        block_numbers = await r.hkeys(self.DB_KEY_POOL_INFO_HASH)

        cache_size = len(block_numbers)
        blocks_to_delete = [b for b in block_numbers if int(b) < min_block or int(b) > top_block]
        self.logger.info(f'Cache size: {cache_size}, entries to delete: {len(blocks_to_delete)}')

        for block_number in blocks_to_delete:
            await r.hdel(self.DB_KEY_POOL_INFO_HASH, block_number)

        self.logger.info('Cache cleared successfully!')

    async def put(self, subkey, pool_map: PoolInfoMap):
        r: Redis = await self.deps.db.get_redis()
        j_pools = json.dumps({key: p.as_dict_brief() for key, p in pool_map.items()})
        await r.hset(self.DB_KEY_POOL_INFO_HASH, str(subkey), j_pools)

    async def get(self, subkey) -> Optional[PoolInfoMap]:
        try:
            r: Redis = await self.deps.db.get_redis()
            cached_item = await r.hget(self.DB_KEY_POOL_INFO_HASH, str(subkey))
            if cached_item:
                raw_dict = json.loads(cached_item)
                pool_map = {k: PoolInfo.from_dict_brief(it) for k, it in raw_dict.items()}
                if all(p is not None for p in pool_map.values()):
                    return pool_map
        except (TypeError, ValueError):
            self.logger.warning(f'Failed to load PoolInfoMap from the cache ({subkey = })')
            return

    async def purge(self):
        r: Redis = await self.deps.db.get_redis()
        await r.delete(self.DB_KEY_POOL_INFO_HASH)

    async def automatic_clear(self):
        # sometimes clear the cache
        self.logger.info('Automatic cache clearing...')
        with suppress(Exception):
            if self._pool_cache_saves % self._pool_cache_clear_every == 0:
                self.logger.info('Clearing the cache...')
                await self.clear(self.pool_cache_max_age)
            self._pool_cache_saves += 1
