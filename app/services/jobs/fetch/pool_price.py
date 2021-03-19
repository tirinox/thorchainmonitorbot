from services.jobs.fetch.base import BaseFetcher
from services.jobs.fetch.fair_price import fair_rune_price
from services.jobs.midgard import get_url_gen_by_network_id
from services.lib.constants import BNB_BUSD_SYMBOL, RUNE_SYMBOL_DET, is_stable_coin
from services.lib.datetime import parse_timespan_to_seconds, DAY, HOUR
from services.lib.depcont import DepContainer
from services.models.pool_info import PoolInfo
from services.models.time_series import PriceTimeSeries


# todo => block number === date map

class PoolPriceFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        cfg = deps.cfg
        period = parse_timespan_to_seconds(cfg.price.fetch_period)
        super().__init__(deps, sleep_period=period)
        self.deps = deps
        self.midgrad_url_gen = get_url_gen_by_network_id(cfg.network)

    async def fetch(self):
        d = self.deps
        await self.get_current_pool_data_full()
        price = d.price_holder.usd_per_rune
        self.logger.info(f'fresh rune price is ${price:.3f}')

        if price > 0:
            price_series = PriceTimeSeries('rune_market_price', d.db)
            await price_series.add(price=price)

            fair_price = await fair_rune_price(d.price_holder)
            fair_price.real_rune_price = price

            deterministic_price_series = PriceTimeSeries(RUNE_SYMBOL_DET, d.db)
            await deterministic_price_series.add(price=fair_price.fair_price)

            return fair_price
        else:
            self.logger.warning(f'really ${price:.3f}? that is odd!')

    async def get_current_pool_data_full(self):
        pool_info_raw = await self.deps.thor_connector.query_pools()
        results = {
            p.asset: PoolInfo(p.asset,
                              p.assets_per_rune, p.balance_asset_int, p.balance_rune_int,
                              p.pool_units_int, p.status)
            for p in pool_info_raw
        }
        if results and self.deps.price_holder is not None:
            self.deps.price_holder.update(results)

        return results

    def url_for_historical_pool_state(self, pool, ts):
        from_ts = int(ts - HOUR)
        to_ts = int(ts + DAY + HOUR)
        return self.midgrad_url_gen.url_for_pool_depth_history(pool, from_ts, to_ts)

    async def get_asset_per_rune_of_pool_by_day(self, pool, day):
        cache_key = f'midg_pool_info:{pool}:{day}'
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
        stable_coin_symbol = BNB_BUSD_SYMBOL  # todo: get price from coin gecko OR from weighted usd price cache
        usd_per_rune = await self.get_asset_per_rune_of_pool_by_day(stable_coin_symbol, day_ts)
        if is_stable_coin(pool):
            return usd_per_rune, 1.0
        else:
            asset_per_rune = await self.get_asset_per_rune_of_pool_by_day(pool, day_ts)
            usd_per_asset = usd_per_rune / asset_per_rune
            return usd_per_rune, usd_per_asset
