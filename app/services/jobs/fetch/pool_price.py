import calendar
import json
from datetime import date, datetime, timedelta
from typing import Optional

from aioredis import Redis

from services.jobs.fetch.base import BaseFetcher
from services.jobs.fetch.fair_price import fair_rune_price
from services.lib.config import Config
from services.lib.constants import BNB_BUSD_SYMBOL, RUNE_SYMBOL_DET, is_stable_coin, NetworkIdents, \
    ETH_USDT_TEST_SYMBOL, RUNE_SYMBOL_MARKET, THOR_BLOCK_TIME, ETH_USDT_SYMBOL
from services.lib.date_utils import parse_timespan_to_seconds, DAY, HOUR, day_to_key
from services.lib.depcont import DepContainer
from services.lib.midgard.parser import get_parser_by_network_id
from services.lib.midgard.urlgen import get_url_gen_by_network_id
from services.models.last_block import LastBlock
from services.models.pool_info import PoolInfoHistoricEntry, parse_thor_pools, PoolInfo, PoolInfoMap
from services.models.time_series import PriceTimeSeries


class PoolPriceFetcher(BaseFetcher):
    """
    This class queries Midgard and THORNodes to get current and historical pool prices and depths
    """

    def __init__(self, deps: DepContainer):
        cfg: Config = deps.cfg
        period = parse_timespan_to_seconds(cfg.price.fetch_period)
        super().__init__(deps, sleep_period=period)
        self.deps = deps
        self.midgard_url_gen = get_url_gen_by_network_id(cfg.network_id)
        self.max_attempts = 5
        self.use_thor_consensus = False

    async def fetch(self):
        d = self.deps

        current_pools = await self.get_current_pool_data_full()

        if current_pools and self.deps.price_holder is not None:
            self.deps.price_holder.update(current_pools)

        price = d.price_holder.usd_per_rune
        self.logger.info(f'fresh rune price is ${price:.3f}')

        if price > 0:
            price_series = PriceTimeSeries(RUNE_SYMBOL_MARKET, d.db)
            await price_series.add(price=price)

            fair_price = await fair_rune_price(d.price_holder)
            fair_price.real_rune_price = price

            deterministic_price_series = PriceTimeSeries(RUNE_SYMBOL_DET, d.db)
            await deterministic_price_series.add(price=fair_price.fair_price)

            return fair_price
        else:
            self.logger.warning(f'really ${price:.3f}? that is odd!')

    async def _fetch_current_pool_data_from_thornodes(self, height=None) -> PoolInfoMap:
        thor_pools = {}
        for attempt in range(1, self.max_attempts):
            try:
                thor_pools = await self.deps.thor_connector.query_pools(height, consensus=self.use_thor_consensus)
            except (TypeError, IndexError):
                self.logger.warning(f'thor_connector.query_pools failed! Attempt: #{attempt}')
                pass
        return parse_thor_pools(thor_pools)

    DB_KEY_POOL_INFO_HASH = 'PoolInfo:hashtable'

    async def _save_to_cache(self, r: Redis, subkey, pool_infos: PoolInfoMap):
        j_pools = json.dumps({key: p.as_dict() for key, p in pool_infos.items()})
        await r.hset(self.DB_KEY_POOL_INFO_HASH, str(subkey), j_pools)

    async def _load_from_cache(self, r: Redis, subkey) -> PoolInfoMap:
        cached_item = await r.hget(self.DB_KEY_POOL_INFO_HASH, str(subkey))
        if cached_item:
            raw_dict = json.loads(cached_item)
            pool_infos = {k: PoolInfo.from_dict(it) for k, it in raw_dict.items()}
            return pool_infos

    @staticmethod
    def _hash_key_day(dt: datetime):
        return day_to_key(dt.date(), 'ByDay')

    async def get_current_pool_data_full(self, height=None, caching=False) -> PoolInfoMap:
        if caching:
            r: Redis = await self.deps.db.get_redis()

            cache_key = height if height else self._hash_key_day(datetime.now())
            pool_infos = await self._load_from_cache(r, cache_key)

            if not pool_infos:
                pool_infos = await self._fetch_current_pool_data_from_thornodes(height)
                await self._save_to_cache(r, cache_key, pool_infos)

            return pool_infos
        else:
            return await self._fetch_current_pool_data_from_thornodes(height)

    async def get_pool_data_full_for_last_days(self, days=14, now=None):
        r: Redis = await self.deps.db.get_redis()

        now = now if now else datetime.now()
        results = []
        for day_no in range(days):
            dt = now - timedelta(days=day_no)
            cache_key = self._hash_key_day(dt)
            pool_infos = await self._load_from_cache(r, cache_key)
            results.append(pool_infos)

        return results

    async def fill_pool_data_full_for_last_days(self, days=14):
        url_last_block = self.midgard_url_gen.url_last_block()
        parser = get_parser_by_network_id(self.deps.cfg.network_id)

        self.logger.info(f"get: {url_last_block}")

        async with self.deps.session.get(url_last_block) as resp:
            raw_data = await resp.json()
            last_block: LastBlock = next(parser.parse_last_block(raw_data).values())
            start_block = last_block.thorchain
            blocks_per_day = DAY / THOR_BLOCK_TIME
            for block in range(start_block, blocks_per_day * (days + 1), -blocks_per_day):
                print(block)  # fixme!

    async def purge_pool_height_cache(self):
        r: Redis = await self.deps.db.get_redis()
        await r.delete(self.DB_KEY_POOL_INFO_HASH)

    def url_for_historical_pool_state(self, pool, ts):
        from_ts = int(ts - HOUR)
        to_ts = int(ts + DAY + HOUR)
        return self.midgard_url_gen.url_for_pool_depth_history(pool, from_ts, to_ts)

    async def get_asset_per_rune_of_pool_by_day(self, pool: str, day: date, caching=True):
        info: PoolInfoHistoricEntry = await self.get_pool_info_by_day(pool, day, caching)
        return info.to_pool_info(pool).asset_per_rune if info else 0.0

    DB_KEY_HISTORIC_POOL = 'MidgardPoolInfoHistoric'

    async def purge_historic_midgard_pool_cache(self):
        r: Redis = await self.deps.db.get_redis()
        await r.delete(self.DB_KEY_HISTORIC_POOL)

    async def get_pool_info_by_day(self, pool: str, day: date, caching=True) -> Optional[PoolInfoHistoricEntry]:
        parser = get_parser_by_network_id(self.deps.cfg.network_id)

        hash_key = ''
        if caching:
            hash_key = day_to_key(day, prefix=pool)
            cached_raw = await self.deps.db.redis.hget(self.DB_KEY_HISTORIC_POOL, hash_key)
            if cached_raw:
                try:
                    j = json.loads(cached_raw)
                    return parser.parse_historic_pool_items(j)[0]
                except ValueError:
                    pass

        timestamp = calendar.timegm(day.timetuple())
        url = self.url_for_historical_pool_state(pool, timestamp)
        self.logger.info(f"get: {url}")

        async with self.deps.session.get(url) as resp:
            raw_data = await resp.json()
            pools_info = parser.parse_historic_pool_items(raw_data)
            if not pools_info:
                self.logger.error(f'there were no historical data returned!')
                return None
            else:
                if caching and raw_data:
                    await self.deps.db.redis.hset(self.DB_KEY_HISTORIC_POOL, hash_key, json.dumps(raw_data))
                pool_info = pools_info[0]
                return pool_info

    async def get_usd_price_of_rune_and_asset_by_day(self, pool, day: date, caching=True):
        network = self.deps.cfg.network_id
        single_action = True
        if network == NetworkIdents.CHAOSNET_BEP2CHAIN:
            stable_coin_symbol = BNB_BUSD_SYMBOL
            single_action = False
        elif network == NetworkIdents.CHAOSNET_MULTICHAIN:
            stable_coin_symbol = ETH_USDT_SYMBOL  # todo: get price from coin gecko OR from weighted usd price cache
        elif network == NetworkIdents.TESTNET_MULTICHAIN:
            stable_coin_symbol = ETH_USDT_TEST_SYMBOL
        else:
            raise NotImplementedError

        if single_action:
            info = await self.get_pool_info_by_day(pool, day, caching)
            usd_per_asset = info.asset_price_usd
            asset_per_rune = info.asset_depth / info.rune_depth
            usd_per_rune = asset_per_rune * usd_per_asset
            return usd_per_rune, usd_per_asset
        else:
            usd_per_rune = await self.get_asset_per_rune_of_pool_by_day(stable_coin_symbol, day, caching=caching)
            if is_stable_coin(pool):
                return usd_per_rune, 1.0
            else:
                asset_per_rune = await self.get_asset_per_rune_of_pool_by_day(pool, day, caching=caching)
                usd_per_asset = usd_per_rune / asset_per_rune
                return usd_per_rune, usd_per_asset
