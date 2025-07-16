from api.midgard.connector import MidgardConnector
from jobs.fetch.cached.base import CachedDataSource
from lib.date_utils import HOUR
from models.swap_history import SwapHistoryResponse


class SwapHistoryFetcher(CachedDataSource[SwapHistoryResponse]):
    """
    Fetches swap history from the cache.
    """

    def __init__(self, mdg: MidgardConnector, cache_period=HOUR):
        super().__init__(cache_period, retry_times=5, retry_exponential_growth_factor=2)
        self.mdg = mdg

    async def _load(self) -> SwapHistoryResponse:
        data = await self.mdg.query_swap_stats(count=15, interval='day')
        if not data:
            raise RuntimeError('Failed to fetch swap history data')
        return data
