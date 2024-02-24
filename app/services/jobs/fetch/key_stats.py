import asyncio

from services.jobs.fetch.base import BaseFetcher
from services.jobs.fetch.flipside.flipside import FlipSideConnector, FSList
from services.jobs.fetch.flipside.urls import *
from services.jobs.fetch.pool_price import PoolFetcher
from services.lib.date_utils import parse_timespan_to_seconds, DAY
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger
from services.models.flipside import FSAffiliateCollectors, FSFees, FSSwapCount, FSLockedValue, FSSwapVolume, \
    FSSwapRoutes, AlertKeyStats

FS_AFFILIATES_V4 = 'query_affiliates_v4.sql'
FS_ROUTES_V2 = 'query_routes_v2.sql'
FS_SWAP_VOL = 'query_swap_vol.sql'
FS_LOCKED_VALUE = 'query_locked_value.sql'
FS_UNIQUE_SWAPPERS = 'query_unique_swappers.sql'
FS_RUNE_EARNINGS = 'query_rune_earnings.sql'


class KeyStatsFetcher(BaseFetcher, WithLogger):
    def __init__(self, deps: DepContainer):
        sleep_period = parse_timespan_to_seconds(deps.cfg.key_metrics.fetch_period)
        super().__init__(deps, sleep_period)
        self._fs = FlipSideConnector(deps.session, deps.cfg.flipside.api_key)
        self.tally_days_period = deps.cfg.as_int('key_metrics.tally_period_days', 7)

        # x3 days (this week + previous week + spare days)
        self.trim_max_days = deps.cfg.as_int('key_metrics.trim_max_days', self.tally_days_period * 3)

    async def fetch(self) -> AlertKeyStats:
        # Load pool data for BTC/ETH value in the pools
        pf: PoolFetcher = self.deps.pool_fetcher
        previous_block = self.deps.last_block_store.block_time_ago(self.tally_days_period * DAY)

        if previous_block < 0:
            raise ValueError(f'Previous block is negative {previous_block}!')

        fresh_pools, old_pools = await asyncio.gather(
            pf.load_pools(),
            pf.load_pools(height=previous_block)
        )

        fresh_pools = pf.convert_pool_list_to_dict(list(fresh_pools.values()))
        old_pools = pf.convert_pool_list_to_dict(list(old_pools.values()))

        routes = await self._fs.request_daily_series_v2(FS_LATEST_SWAP_PATH_URL, FSSwapRoutes)
        routes = routes.most_recent

        # Load all FlipSideCrypto data
        # loaders = [
        #     (FS_RUNE_EARNINGS, FSFees, None),
        #     (FS_UNIQUE_SWAPPERS, FSSwapCount, None),
        #     (FS_LOCKED_VALUE, FSLockedValue, None),
        #     (FS_SWAP_VOL, FSSwapVolume, None),
        #     (FS_AFFILIATES_V4, FSAffiliateCollectors, None),
        # ]
        #
        # # Actual API requests
        # data_chunks = await asyncio.gather(
        #     *[self._fs.request_daily_series_sql_file(sql_file, max_days=self.trim_max_days)
        #       for sql_file, klass, _ in loaders]
        # )

        loaders = [
            (FS_LATEST_EARNINGS_URL, FSFees),
            (FS_LATEST_SWAP_COUNT_URL, FSSwapCount),
            (FS_LATEST_LOCKED_RUNE_URL, FSLockedValue),
            (FS_LATEST_SWAP_VOL_URL, FSSwapVolume),
            (FS_LATEST_SWAP_AFF_FEE_URL, FSAffiliateCollectors),
        ]

        # Actual API requests
        data_chunks = await asyncio.gather(
            *[self._fs.request_daily_series_v2(url, klass) for url, klass in loaders]
        )

        # Convert JSON to FSxx objects
        # transformed_data_chunks = [
        #     batch.transform_from_json(klass, f or 'from_json_lowercase')
        #     for batch, (_, klass, f) in zip(data_chunks, loaders)
        # ]

        # Merge data streams
        result = FSList.combine(*data_chunks)

        # Done. Construct the resulting event
        return AlertKeyStats(
            result, old_pools, fresh_pools,
            routes,
            days=self.tally_days_period
        )
