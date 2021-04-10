import logging
from abc import abstractmethod
from typing import List, Tuple, NamedTuple, Dict

from services.jobs.fetch.pool_price import PoolPriceFetcher
from services.lib.midgard.urlgen import MidgardURLGenBase
from services.lib.depcont import DepContainer
from services.models.lp_info import LiquidityPoolReport, LPDailyGraphPoint


class YieldSummary(NamedTuple):
    reports: List[LiquidityPoolReport]
    charts: Dict[str, List[LPDailyGraphPoint]]


class AsgardConsumerConnectorBase:
    def __init__(self, deps: DepContainer, ppf: PoolPriceFetcher, url_gen: MidgardURLGenBase):
        self.deps = deps
        self.logger = logging.getLogger(self.__class__.__name__)
        self.ppf = ppf
        self.url_gen = url_gen

    # interface
    @abstractmethod
    async def generate_yield_summary(self, address, pools: List[str]) -> Tuple[dict, List[LiquidityPoolReport]]:
        ...

    # interface
    @abstractmethod
    async def generate_yield_report_single_pool(self, address, pool) -> LiquidityPoolReport:
        ...

    # interface
    @abstractmethod
    async def get_my_pools(self, address) -> List[str]:
        ...
