import asyncio

from services.jobs.fetch.base import BaseFetcher
from services.jobs.fetch.flipside import FlipSideConnector, FSList
from services.jobs.fetch.pool_price import PoolFetcher
from services.lib.date_utils import parse_timespan_to_seconds, DAY
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger
from services.models.flipside import FSAffiliateCollectors, FSFees, FSSwapCount, FSLockedValue, FSSwapVolume, \
    FSSwapRoutes, EventKeyStats

URL_FS_AFFILIATE_AGENTS = "https://api.flipsidecrypto.com/api/v2/queries/541f964d-44d0-448f-b666-ffe4bfe7b50a/data/latest"
URL_FS_RUNE_EARNINGS = "https://api.flipsidecrypto.com/api/v2/queries/6b27035e-f56f-4a7d-91f2-46995fc71a20/data/latest"
URL_FS_UNIQUE_SWAPPERS = 'https://api.flipsidecrypto.com/api/v2/queries/425f0bb7-f875-41cd-a7cb-ed0427d5bff0/data/latest'
URL_FS_LOCKED_VALUE = 'https://api.flipsidecrypto.com/api/v2/queries/37f64aee-ef96-4833-a5fa-b9deb60a676a/data/latest'
URL_FS_SWAP_VOL = 'https://api.flipsidecrypto.com/api/v2/queries/ee1f4915-988d-4920-99c0-e9346d0bb07c/data/latest'
URL_FS_ROUTES = 'https://api.flipsidecrypto.com/api/v2/queries/e999ee41-f72b-4ce8-8ab1-ff2f36545d2a/data/latest'


class KeyStatsFetcher(BaseFetcher, WithLogger):
    def __init__(self, deps: DepContainer):
        sleep_period = parse_timespan_to_seconds(deps.cfg.key_metrics.fetch_period)
        super().__init__(deps, sleep_period)
        self._fs = FlipSideConnector(deps.session)
        self.tally_days_period = deps.cfg.as_int('key_metrics.tally_period_days', 7)

        # x2 days
        self.trim_max_days = deps.cfg.as_int('key_metrics.trim_max_days', self.tally_days_period * 2)

    async def fetch(self) -> EventKeyStats:
        # Load all FlipSideCrypto data
        loaders = [
            (URL_FS_AFFILIATE_AGENTS, FSAffiliateCollectors),
            (URL_FS_RUNE_EARNINGS, FSFees),
            (URL_FS_UNIQUE_SWAPPERS, FSSwapCount),
            (URL_FS_LOCKED_VALUE, FSLockedValue),
            (URL_FS_SWAP_VOL, FSSwapVolume),
            (URL_FS_ROUTES, FSSwapRoutes),
        ]

        # Actual API requests
        data_chunks = await asyncio.gather(
            *[self._fs.request_daily_series(url, max_days=self.trim_max_days) for url, klass in loaders]
        )

        # Convert JSON to FSxx objects
        transformed_data_chunks = [
            batch.transform_from_json(klass)
            for batch, (_, klass) in zip(data_chunks, loaders)
        ]

        # Merge data streams
        result = FSList.combine(*transformed_data_chunks)

        # Load pool data for BTC/ETH value in the pools
        pf: PoolFetcher = self.deps.pool_fetcher
        previous_block = self.deps.last_block_store.block_time_ago(self.tally_days_period * DAY)
        fresh_pools, old_pools = await asyncio.gather(
            pf.load_pools(),
            pf.load_pools(height=previous_block)
        )

        # Done. Construct the resulting event
        return EventKeyStats(
            result, old_pools, fresh_pools, days=self.tally_days_period
        )
