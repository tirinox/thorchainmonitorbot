from services.fetch.base import BaseFetcher
from services.fetch.fair_price import fair_rune_price
from services.fetch.midgard import get_midgard_url
from services.lib.datetime import parse_timespan_to_seconds, DAY, HOUR
from services.lib.depcont import DepContainer
from services.models.pool_info import PoolInfo
from services.models.time_series import PriceTimeSeries, TimeSeries
from services.lib.constants import BUSD_SYMBOL, RUNE_SYMBOL, RUNE_SYMBOL_DET


class PoolPriceFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        cfg = deps.cfg
        period = parse_timespan_to_seconds(cfg.price.fetch_period)
        super().__init__(deps, sleep_period=period)
        self.deps = deps
        self.pool_series = TimeSeries('pool-info', self.deps.db)

    @staticmethod
    def historic_url(asset, height):
        return f"/thorchain/pool/{asset}?height={height}"

    @staticmethod
    def full_pools_url():
        return f"/thorchain/pools"

    # todo: v2 compatibility
    def url_for_historical_pool_state(self, pool, ts):
        from_ts = int(ts - HOUR)
        to_ts = int(ts + DAY + HOUR)
        query = f"/history/pools?pool={pool}&interval=day&from={from_ts}&to={to_ts}"
        return get_midgard_url(self.deps.cfg, query)

    async def fetch(self):
        d = self.deps
        await self.get_current_pool_data_full()
        price = d.price_holder.usd_per_rune
        self.logger.info(f'fresh rune price is ${price:.3f}')

        # if new_pool_info:
        #     await self._save_historical_pool_data(new_pool_info)

        if price > 0:
            pts = PriceTimeSeries(RUNE_SYMBOL, d.db)
            await pts.add(price=price)

            pts_det = PriceTimeSeries(RUNE_SYMBOL_DET, d.db)
            fair_price = await fair_rune_price(d.price_holder)
            await pts_det.add(price=fair_price.fair_price)
            fair_price.real_rune_price = price
            return fair_price
        else:
            self.logger.warning(f'really ${price:.3f}? that is odd!')

    async def fetch_pool_data_historic(self, asset, height=0) -> PoolInfo:
        if asset == RUNE_SYMBOL:
            return PoolInfo.dummy()

        url = self.historic_url(asset, height)
        pool_info_raw = await self.deps.thor_nodes.request(url)
        return PoolInfo.from_dict(pool_info_raw)

    async def get_price_in_rune(self, asset, height=0):
        if asset == RUNE_SYMBOL:
            return 1.0
        asset_pool = await self.fetch_pool_data_historic(asset, height)
        asset_per_rune = asset_pool.balance_asset / asset_pool.balance_rune
        return asset_per_rune

    async def get_historical_price(self, asset, height=0):
        dollar_per_rune = await self.get_price_in_rune(BUSD_SYMBOL, height)
        asset_per_rune = await self.get_price_in_rune(asset, height)

        asset_price_in_usd = dollar_per_rune / asset_per_rune

        return dollar_per_rune, asset_price_in_usd

    async def _save_historical_pool_data(self, pool_info_dict):
        await self.pool_series.add_as_json(j={
            pool: info.as_dict for pool, info in pool_info_dict.items()
        })

    async def get_current_pool_data_full(self):
        pool_info_raw = await self.deps.thor_nodes.request(self.full_pools_url())
        results = {
            pool['asset']: PoolInfo.from_dict(pool) for pool in pool_info_raw
        }
        if results and self.deps.price_holder is not None:
            self.deps.price_holder.update(results)

        return results

    async def get_prices_of(self, asset_list):
        pool_dict = await self.get_current_pool_data_full()
        return {
            asset: pool for asset, pool in pool_dict.items() if pool in asset_list
        }

    @staticmethod
    def cache_key_for_pool_info_by_day(pool, day):
        return f'midg_pool_info:{pool}:{day}'

    async def get_asset_per_rune_of_pool_by_day(self, pool, day):
        cache_key = self.cache_key_for_pool_info_by_day(pool, day)
        cached_raw = await self.deps.db.redis.get(cache_key)
        if cached_raw:
            try:
                return float(cached_raw)
            except ValueError:
                pass

        url = self.url_for_historical_pool_state(pool, day)
        self.logger.info(f"get: {url}")

        async with self.deps.session.get(url) as resp:
            pools_info = await resp.json()
            if not pools_info:
                self.logger.warning(f'fetch result = []!')
            pool_info = pools_info[0]
            price = int(pool_info['assetDepth']) / int(pool_info['runeDepth'])
            await self.deps.db.redis.set(cache_key, price)
            return price

    async def get_usd_per_rune_asset_per_rune_by_day(self, pool, day_ts):
        usd_per_rune = await self.get_asset_per_rune_of_pool_by_day(BUSD_SYMBOL, day_ts)
        if pool == BUSD_SYMBOL:
            return usd_per_rune, 1.0
        else:
            asset_per_rune = await self.get_asset_per_rune_of_pool_by_day(pool, day_ts)
            usd_per_asset = usd_per_rune / asset_per_rune
            return usd_per_rune, usd_per_asset
