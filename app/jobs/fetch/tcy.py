from jobs.fetch.base import BaseFetcher
from lib.depcont import DepContainer



class TCYInfoFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        period = deps.cfg.as_interval('tcy.fetch_period', '1h')
        super().__init__(deps, sleep_period=period)
        self.deps = deps

    async def fetch(self):
        pass


    # stake earning = interval.liquidityFees / 1e8 * 10% * runePriceUSD

