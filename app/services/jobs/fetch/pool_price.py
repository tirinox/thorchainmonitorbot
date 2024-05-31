import json
from contextlib import suppress
from random import random
from typing import Optional, List, Dict

from redis.asyncio import Redis

from services.jobs.fetch.base import BaseFetcher
from services.lib.config import Config
from services.lib.constants import RUNE_SYMBOL_DET, RUNE_SYMBOL_POOL, RUNE_SYMBOL_CEX, THOR_BLOCK_TIME
from services.lib.date_utils import parse_timespan_to_seconds, DAY
from services.lib.depcont import DepContainer
from services.lib.midgard.parser import get_parser_by_network_id
from services.lib.midgard.urlgen import free_url_gen
from services.models.pool_info import parse_thor_pools, PoolInfo, PoolInfoMap
from services.models.price import RuneMarketInfo
from services.models.time_series import PriceTimeSeries


class PoolFetcher(BaseFetcher):
    """
    This class queries Midgard and THORNodes to get current and historical pool prices and depths
    """

    # todo: split this class: 1) PoolFetcher 2) PoolDataCache 3) RuneMarketInfoFetcher
    CACHE_TOLERANCE = 60

    def __init__(self, deps: DepContainer):
        assert deps
        cfg: Config = deps.cfg
        period = parse_timespan_to_seconds(cfg.price.fetch_period)

        super().__init__(deps, sleep_period=period)

        self.pool_cache_max_age = parse_timespan_to_seconds(cfg.price.pool_cache_max_age)
        assert self.pool_cache_max_age > 0
        self.deps = deps
        self.use_thor_consensus = False
        self.parser = get_parser_by_network_id(self.deps.cfg.network_id)
        self.price_history_max_points = 200000
        self._pool_cache_saves = 0
        self._pool_cache_clear_every = 1000

    async def fetch(self) -> RuneMarketInfo:
        current_pools = await self.reload_global_pools()

        price = self.deps.price_holder.usd_per_rune
        self.logger.info(f'Fresh rune price is ${price:.3f}, {len(current_pools)} total pools')

        rune_market_info: RuneMarketInfo = await self.deps.rune_market_fetcher.get_rune_market_info()
        if rune_market_info:
            rune_market_info.pools = current_pools
            await self._write_price_time_series(rune_market_info)

        # sometimes clear the cache
        with suppress(Exception):
            if self._pool_cache_saves % self._pool_cache_clear_every == 0:
                self.logger.info('Clearing the cache...')
                await self.clear_cache(self.pool_cache_max_age)
            self._pool_cache_saves += 1

        return rune_market_info

    async def reload_global_pools(self) -> PoolInfoMap:
        price_holder = self.deps.price_holder

        current_pools = await self.load_pools()

        assert price_holder is not None

        # store into the global state
        if current_pools:
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
            pool_price_series = PriceTimeSeries(RUNE_SYMBOL_POOL, db)
            await pool_price_series.add(price=rune_market_info.pool_rune_price)
            await pool_price_series.trim_oldest(self.price_history_max_points)
        else:
            self.logger.error(f'Odd {rune_market_info.pool_rune_price = }')

        # CEX price fill
        if rune_market_info.cex_price and rune_market_info.cex_price > 0:
            cex_price_series = PriceTimeSeries(RUNE_SYMBOL_CEX, db)
            await cex_price_series.add(price=rune_market_info.cex_price)
            await cex_price_series.trim_oldest(self.price_history_max_points)
        else:
            self.logger.error(f'Odd {rune_market_info.cex_price = }')

        # Deterministic price fill
        if rune_market_info.fair_price and rune_market_info.fair_price > 0:
            deterministic_price_series = PriceTimeSeries(RUNE_SYMBOL_DET, db)
            await deterministic_price_series.add(price=rune_market_info.fair_price)
            await deterministic_price_series.trim_oldest(self.price_history_max_points)
        else:
            self.logger.error(f'Odd {rune_market_info.fair_price = }')

    async def _fetch_current_pool_data_from_thornode(self, height=None) -> PoolInfoMap:
        try:
            thor_pools = await self.deps.thor_connector.query_pools(height)
            return parse_thor_pools(thor_pools)
        except (TypeError, IndexError) as e:
            self.logger.error(f'thor_connector.query_pools failed! Err: {e}')

        return {}

    DB_KEY_POOL_INFO_HASH = 'PoolInfo:hashtable_v2'

    async def clear_cache(self, max_age=1000 * DAY):
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

    async def _save_to_cache(self, r: Redis, subkey, pool_map: PoolInfoMap):
        j_pools = json.dumps({key: p.as_dict_brief() for key, p in pool_map.items()})
        await r.hset(self.DB_KEY_POOL_INFO_HASH, str(subkey), j_pools)

    async def _load_from_cache(self, r: Redis, subkey) -> Optional[PoolInfoMap]:
        try:
            cached_item = await r.hget(self.DB_KEY_POOL_INFO_HASH, str(subkey))
            if cached_item:
                raw_dict = json.loads(cached_item)
                pool_map = {k: PoolInfo.from_dict_brief(it) for k, it in raw_dict.items()}
                if all(p is not None for p in pool_map.values()):
                    return pool_map
        except (TypeError, ValueError):
            self.logger.warning(f'Failed to load PoolInfoMap from the cache ({subkey = })')
            return

    async def load_pools(self, height=None, caching=True, usd_per_rune=None) -> PoolInfoMap:
        if caching:
            r: Redis = await self.deps.db.get_redis()

            if height is None:
                # latest
                pool_map = await self._fetch_current_pool_data_from_thornode()
                cache_key = self.deps.last_block_store.thor
                await self._save_to_cache(r, cache_key, pool_map)
            else:
                pool_map = await self._load_from_cache(r, height)
                if not pool_map:
                    pool_map = await self._fetch_current_pool_data_from_thornode(height)
                    await self._save_to_cache(r, height, pool_map)
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

    async def purge_pool_height_cache(self):
        r: Redis = await self.deps.db.get_redis()
        await r.delete(self.DB_KEY_POOL_INFO_HASH)

    _dbg_flag = 1

    @classmethod
    def _dbg_add_thor_pools(cls, current_pools: PoolInfoMap):
        if cls._dbg_flag < 3:
            cls._dbg_flag += 1
            return

        p1 = current_pools.get('BNB.BNB').copy()
        p1.asset = 'THOR.BNB'
        p2 = current_pools.get('BTC.BTC').copy()
        p2.asset = 'THOR.BTC'
        p3 = current_pools.get('ETH.ETH').copy()
        p3.asset = 'THOR.ETH'
        for p in (p1, p2, p3):
            current_pools[p.asset] = p

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
        raw_data = await self.deps.midgard_connector.request(free_url_gen.url_pool_info(period=period))
        if not raw_data:
            return
        self.last_raw_result = raw_data
        return self.parser.parse_pool_info(raw_data)

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
