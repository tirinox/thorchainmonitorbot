from api.midgard.connector import MidgardConnector
from jobs.fetch.cached.base import CachedDataSource
from lib.date_utils import HOUR
from models.swap_history import SwapHistoryResponse, SwapsHistoryEntry


class SwapHistoryFetcher(CachedDataSource[SwapHistoryResponse]):
    """
    Fetches swap history from the cache.
    """

    def __init__(self, mdg: MidgardConnector, cache_period=HOUR, pool=None):
        # pool = None means all pools, otherwise it filters by the specified pool
        super().__init__(cache_period, retry_times=5, retry_exponential_growth_factor=2)
        self.mdg = mdg
        self.pool = pool

    async def _load(self) -> SwapHistoryResponse:
        data = await self.mdg.query_swap_stats(count=15, interval='day', pool=self.pool)
        if not data:
            raise RuntimeError('Failed to fetch swap history data')
        return data.with_last_day_dropped

    async def today(self) -> SwapsHistoryEntry:
        data = await self.get()
        return data.intervals[-1]

    async def yesterday(self) -> SwapsHistoryEntry:
        data = await self.get()
        return data.intervals[-2] if len(data.intervals) > 1 else SwapsHistoryEntry.zero()

    async def this_week(self) -> SwapHistoryResponse:
        data = await self.get()
        return SwapHistoryResponse(
            intervals=data.intervals[-7:],
            meta=data.meta
        )

    async def previous_week(self) -> SwapHistoryResponse:
        data = await self.get()
        return SwapHistoryResponse(
            intervals=data.intervals[-14:-7],
            meta=data.meta
        )
