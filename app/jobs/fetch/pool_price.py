import json
from contextlib import suppress
from random import random
from typing import Optional, List, Dict

from redis.asyncio import Redis
from ujson import JSONDecodeError

from api.midgard.parser import get_parser_by_network_id
from jobs.fetch.base import BaseFetcher
from lib.config import Config
from lib.constants import RUNE_SYMBOL_DET, RUNE_SYMBOL_POOL, RUNE_SYMBOL_CEX, THOR_BLOCK_TIME
from lib.date_utils import parse_timespan_to_seconds, DAY
from lib.depcont import DepContainer
from lib.logs import WithLogger
from models.pool_info import parse_thor_pools, PoolInfo, PoolInfoMap
from models.price import RuneMarketInfo
from models.time_series import PriceTimeSeries


class PoolFetcher(BaseFetcher):
    """
    This class queries Midgard and THORNodes to get current and historical pool prices and depths
    """

    # todo: split this class: 1) PoolFetcher 2) PoolDataCache (v) 3) RuneMarketInfoFetcher
    CACHE_TOLERANCE = 60

    def __init__(self, deps: DepContainer):
        assert deps
        cfg: Config = deps.cfg
        period = parse_timespan_to_seconds(cfg.price.fetch_period)

        super().__init__(deps, sleep_period=period)

        self.deps = deps
        self.parser = get_parser_by_network_id(self.deps.cfg.network_id)
        self.price_history_max_points = 200000
        self.cache = PoolCache(deps)

    async def fetch(self) -> RuneMarketInfo:
        current_pools = await self.reload_global_pools()

        price = self.deps.price_holder.usd_per_rune
        self.logger.info(f'Fresh rune price is ${price:.3f}, {len(current_pools)} total pools')

        rune_market_info: RuneMarketInfo = await self.deps.rune_market_fetcher.get_rune_market_info()
        if rune_market_info:
            rune_market_info.pools = current_pools
            await self._write_price_time_series(rune_market_info)

        # sometimes clear the cache
        await self.cache.automatic_clear()

        return rune_market_info

    async def reload_global_pools(self) -> PoolInfoMap:
        """
        Loads pools and store them into deps.price_holder
        Returns: PoolInfoMap
        """
        price_holder = self.deps.price_holder

        current_pools = await self.load_pools()

        assert price_holder is not None

        # store into the global state
        if current_pools:
            # todo: move it into the graph
            price_holder.update(current_pools)

        return price_holder.pool_info_map

    async def _write_price_time_series(self, rune_market_info: RuneMarketInfo):
        if not rune_market_info:
            self.logger.error('No rune_market_info!')
            return

        if self.deps.price_holder:
            rune_market_info.pool_rune_price = self.deps.price_holder.usd_per_rune

        db = self.deps.db

        # Pool price fill
        if rune_market_info.pool_rune_price and rune_market_info.pool_rune_price > 0:
            pool_price_series = PriceTimeSeries(RUNE_SYMBOL_POOL, db, max_len=self.price_history_max_points)
            await pool_price_series.add(price=rune_market_info.pool_rune_price)
        else:
            self.logger.error(f'Odd {rune_market_info.pool_rune_price = }')

        # CEX price fill
        if rune_market_info.cex_price and rune_market_info.cex_price > 0:
            cex_price_series = PriceTimeSeries(RUNE_SYMBOL_CEX, db, max_len=self.price_history_max_points)
            await cex_price_series.add(price=rune_market_info.cex_price)
        else:
            self.logger.error(f'Odd {rune_market_info.cex_price = }')

        # Deterministic price fill
        if rune_market_info.fair_price and rune_market_info.fair_price > 0:
            deterministic_price_series = PriceTimeSeries(RUNE_SYMBOL_DET, db, max_len=self.price_history_max_points)
            await deterministic_price_series.add(price=rune_market_info.fair_price)
        else:
            self.logger.error(f'Odd {rune_market_info.fair_price = }')

    async def _fetch_current_pool_data_from_thornode(self, height=None) -> PoolInfoMap:
        try:
            thor_pools = await self.deps.thor_connector.query_pools(height)

            # try to get from archive
            if not thor_pools:
                thor_pools = await self.deps.thor_connector_archive.query_pools(height)

            return parse_thor_pools(thor_pools)
        except (TypeError, IndexError, JSONDecodeError) as e:
            self.logger.error(f'thor_connector.query_pools failed! Err: {e} at {height = }')

        return {}

    async def load_pools(self, height=None, caching=True, usd_per_rune=None) -> PoolInfoMap:
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

        self.fill_usd_in_pools(pool_map, usd_per_rune)
        return pool_map

    @staticmethod
    def fill_usd_in_pools(pool_map: PoolInfoMap, usd_per_rune):
        if pool_map and usd_per_rune:
            for pool in pool_map.values():
                pool: PoolInfo
                pool.fill_usd_per_asset(usd_per_rune)

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
