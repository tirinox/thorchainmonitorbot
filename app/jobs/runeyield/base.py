from abc import abstractmethod
from typing import List, NamedTuple, Dict

from lib.depcont import DepContainer
from lib.logs import WithLogger
from models.lp_info import LiquidityPoolReport, LPDailyGraphPoint
from models.pool_member import PoolMemberDetails


class YieldSummary(NamedTuple):
    reports: List[LiquidityPoolReport]
    charts: Dict[str, List[LPDailyGraphPoint]]


class AsgardConsumerConnectorBase(WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

    # interface
    @abstractmethod
    async def generate_yield_summary(self, address, pools: List[str]) -> YieldSummary:
        ...

    # interface
    @abstractmethod
    async def generate_yield_report_single_pool(self, address, pool, user_txs=None) -> LiquidityPoolReport:
        ...

    # interface
    @abstractmethod
    async def get_my_pools(self, address) -> List[PoolMemberDetails]:
        ...
