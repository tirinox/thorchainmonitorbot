import json
from contextlib import suppress
from json import JSONDecodeError
from typing import Optional, List, Dict

from redis.asyncio import Redis
from tqdm import tqdm

from jobs.fetch.cached.base import CachedDataSource
from lib.constants import THOR_BLOCK_TIME
from lib.date_utils import parse_timespan_to_seconds, DAY
from lib.depcont import DepContainer
from lib.utils import grouper, parallel_run_in_groups
from models.pool_info import PoolInfo, PoolInfoMap, parse_thor_pools
from models.price import PriceHolder


class PoolCache(CachedDataSource[PriceHolder]):
    def __init__(self, deps: DepContainer):
        super().__init__(cache_period=THOR_BLOCK_TIME, retry_times=5, retry_exponential_growth_factor=2)
        self.deps = deps
        self._pool_cache_saves = 0
        self._pool_cache_clear_every = 1000

        self.stable_coins = deps.cfg.stable_coins

        self.pool_cache_max_age = parse_timespan_to_seconds(deps.cfg.price.pool_cache_max_age)
        assert self.pool_cache_max_age > 0

    async def get_usd_per_rune(self) -> float:
        ph = await self.deps.pool_cache.get()
        if not ph or not ph.usd_per_rune:
            raise RuntimeError('USD per RUNE is not available in the pool cache!')
        return ph.usd_per_rune

    async def get_pools(self) -> PoolInfoMap:
        """
        Get the current pools from the cache.
        If the cache is empty, it will fetch the pools from THORChain.
        """
        ph = await self.deps.pool_cache.get()
        if not ph or not ph.pool_info_map:
            self.logger.warning('Pool cache is empty! Fetching pools from THORChain...')
            ph = await self._load()
        return ph.pool_info_map

    async def _load(self) -> PriceHolder:
        current_pools = await self.load_pools()

        # sometimes clear the cache
        await self.automatic_clear()

        ph = PriceHolder(self.stable_coins)
        ph.update_pools(current_pools)
        return ph

    async def load_as_price_holder(self, height, caching=True) -> PriceHolder:
        pool_map = await self.load_pools(height=height, caching=caching)
        ph = PriceHolder(self.stable_coins)
        ph.update_pools(pool_map)
        return ph

    async def load_pools(self, height=None, caching=True) -> PoolInfoMap:
        if caching:
            if height is None:
                # latest
                pool_map = await self._fetch_pool_data_from_thornode()
                cache_key = await self.deps.last_block_cache.get_thor_block()
                if cache_key:
                    await self._save_historic_data(cache_key, pool_map)
                else:
                    self.logger.error(f'Last thor block = {cache_key}. Cannot save to cache!')
            else:
                pool_map = await self._load_history_data(subkey=height)
                if not pool_map:
                    pool_map = await self._fetch_pool_data_from_thornode(height)
                    await self._save_historic_data(height, pool_map)
        else:
            pool_map = await self._fetch_pool_data_from_thornode(height)
        return pool_map

    async def _fetch_pool_data_from_thornode(self, height=None) -> PoolInfoMap:
        try:
            thor_pools = await self.deps.thor_connector.query_pools(height)

            # in case of empty response, try to load from the archive
            if not thor_pools:
                thor_pools = await self.deps.thor_connector_archive.query_pools(height)

            # still empty?
            if not thor_pools:
                raise RuntimeError(f'No thor pools found for height {height}!')

            return parse_thor_pools(thor_pools)
        except (TypeError, IndexError, JSONDecodeError) as e:
            self.logger.error(f'thor_connector.query_pools failed! Err: {e} at {height = }')
            raise

    @staticmethod
    def convert_pool_list_to_dict(pool_list: List[PoolInfo]) -> Dict[str, PoolInfo]:
        return {p.asset: p for p in pool_list} if pool_list else None

    async def load_historic_data(self,
                                 blocks_ago,
                                 block_interval: int = 10,
                                 forced=False,
                                 group_size=10,
                                 use_tqdm=False):
        current_block = await self.deps.last_block_cache.get_thor_block()
        if not current_block:
            raise RuntimeError(f'current_block = {current_block}. Cannot load historic data!')

        block_heights = list(range(current_block, current_block - blocks_ago, -abs(block_interval)))

        async def load_for_block(block_no):
            pool_map = await self.load_pools(height=block_no, caching=not forced)
            if not pool_map:
                self.logger.warning(f'Pool map is empty for block #{block_no}. Skipping...')
            return pool_map

        tasks = [load_for_block(block_no) for block_no in block_heights]

        results = await parallel_run_in_groups(
            tasks,
            group_size=group_size,
            delay=0.0,
            use_tqdm=use_tqdm
        )

        return results  # Optionally, filter or process this further

    DB_KEY_POOL_INFO_HASH = 'PoolInfo:hashtable_v2'

    async def clear(self, max_age=1000 * DAY):
        r: Redis = await self.deps.db.get_redis()

        top_block = await self.deps.last_block_cache.get_thor_block()
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

    async def _save_historic_data(self, subkey, pool_map: PoolInfoMap):
        if not pool_map:
            self.logger.warning(f'Pool map is empty for {subkey = }. Cannot save to cache!')
            return

        if not subkey:
            self.logger.error('Subkey is empty! Cannot save to cache!')
            return

        r: Redis = await self.deps.db.get_redis()
        j_pools = json.dumps({key: p.to_dict() for key, p in pool_map.items()})
        await r.hset(self.DB_KEY_POOL_INFO_HASH, str(subkey), j_pools)

    async def _load_history_data(self, subkey) -> Optional[PoolInfoMap]:
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
            return None

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

    async def scan_all_keys(self, hash_name=DB_KEY_POOL_INFO_HASH, scan_batch_size: int = 1000):
        r = await self.deps.db.get_redis()
        cursor = 0
        while True:
            cursor, data = await r.hscan(name=hash_name, cursor=cursor, count=scan_batch_size)
            if cursor == 0:
                break
            for block_no, v in data.items():
                yield int(block_no), v

    async def get_thin_out_keys(self,
                                min_distance: int = 10,
                                scan_batch_size: int = 10000,
                                max_keys_to_delete: int = 10000,
                                ) -> list[str]:
        r = await self.deps.db.get_redis()
        hash_name = self.DB_KEY_POOL_INFO_HASH

        # 1. Stream keys via HSCAN and collect all block heights
        cursor = 0
        block_heights = []

        # We don’t know total size, so we use tqdm without total
        pbar = tqdm(desc="Scanning Redis hash", unit="keys")

        while True:
            cursor, data = await r.hscan(name=hash_name, cursor=cursor, count=scan_batch_size)
            new_keys = 0

            for key in data.keys():
                try:
                    block_heights.append(int(key))
                    new_keys += 1
                except ValueError:
                    continue

            pbar.update(new_keys)

            if len(block_heights) >= max_keys_to_delete:
                self.logger.warning(f"Reached max keys to delete: {max_keys_to_delete}. Stopping scan.")
                break

            if cursor == 0:
                break

        pbar.close()

        # 2. Sort all block heights globally
        self.logger.info(f'Found {len(block_heights)} thin out keys. Sorting...')
        block_heights.sort()

        # 3. Thin the list based on min_distance
        kept = []
        last = None
        for h in block_heights:
            if last is None or h - last >= min_distance:
                kept.append(h)
                last = h

        # 4. Compute deletion list
        kept_set = set(str(k) for k in kept)
        all_keys_str = set(str(h) for h in block_heights)
        to_delete = list(all_keys_str - kept_set)

        return to_delete

    async def backup_hash(self,
                          hash_name: str = DB_KEY_POOL_INFO_HASH,
                          backup_name: str = "",
                          scan_batch_size: int = 1000
                          ):
        r = await self.deps.db.get_redis()

        backup_name = backup_name or f"{hash_name}__backup"
        cursor = 0

        while True:
            cursor, data = await r.hscan(name=hash_name, cursor=cursor, count=scan_batch_size)
            if data:
                await r.hset(backup_name, mapping=data)
            if cursor == 0:
                break

        self.logger.info(f"Backed up hash '{hash_name}' to '{backup_name}' with batched copy.")

    async def delete_keys_batched(self, keys):
        if not keys:
            self.logger.warning("No keys to delete.")
            return

        r = await self.deps.db.get_redis()
        for batch in tqdm(grouper(1000, keys)):
            await r.hdel(self.DB_KEY_POOL_INFO_HASH, *batch)
