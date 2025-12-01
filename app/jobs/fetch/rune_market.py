from jobs.fetch.base import BaseFetcher
from lib.depcont import DepContainer
from models.price import RuneMarketInfo


class RuneMarketInfoFetcher(BaseFetcher):
    async def fetch(self) -> RuneMarketInfo:
        market_info = await self.deps.market_info_cache.get()
        return market_info

    def __init__(self, deps: DepContainer):
        period = deps.cfg.as_interval('price.market_fetch_period', '8m')
        super().__init__(deps, sleep_period=period)
