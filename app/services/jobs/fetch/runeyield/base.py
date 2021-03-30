import asyncio
import logging
from abc import abstractmethod
from typing import List

from services.jobs.fetch.pool_price import PoolPriceFetcher
from services.jobs.midgard import MidgardURLGenBase
from services.lib.depcont import DepContainer
from services.models.stake_info import CurrentLiquidity, StakePoolReport


class AsgardConsumerConnectorBase:
    def __init__(self, deps: DepContainer, ppf: PoolPriceFetcher, url_gen: MidgardURLGenBase):
        self.deps = deps
        self.logger = logging.getLogger(self.__class__.__name__)
        self.ppf = ppf
        self.url_gen = url_gen

    async def generate_yield_summary(self, address, pools: List[str]):
        liqs = await self._fetch_all_pool_liquidity_info(address, pools)
        pools = list(liqs.keys())
        liqs = list(liqs.values())
        weekly_charts = await self._fetch_all_pools_weekly_charts(address, pools)
        stake_reports = await self._generate_yield_reports(liqs)
        return stake_reports, weekly_charts

    async def generate_yield_report_single_pool(self, address, pool):
        liq = await self._fetch_one_pool_liquidity_info(address, pool)
        stake_report = await self._generate_yield_report(liq)
        return stake_report

    async def _generate_yield_reports(self, liqs: List[CurrentLiquidity]) -> List[StakePoolReport]:
        result = await asyncio.gather(*[self._generate_yield_report(liq) for liq in liqs])
        return list(result)

    @abstractmethod
    async def get_my_pools(self, address):
        ...

    @abstractmethod
    async def _fetch_one_pool_liquidity_info(self, address, pool):
        ...

    @abstractmethod
    async def _generate_yield_report(self, liq: CurrentLiquidity) -> StakePoolReport:
        ...

    @abstractmethod
    async def _fetch_all_pool_liquidity_info(self, address, my_pools=None) -> dict:
        ...

    @abstractmethod
    async def _fetch_all_pools_weekly_charts(self, address, pools):
        ...
