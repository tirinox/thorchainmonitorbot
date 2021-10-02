import logging
from abc import abstractmethod
from typing import List, NamedTuple, Dict

from services.lib.depcont import DepContainer
from services.lib.midgard.urlgen import MidgardURLGenBase, MidgardURLGenV2
from services.lib.utils import class_logger
from services.models.lp_info import LiquidityPoolReport, LPDailyGraphPoint


class YieldSummary(NamedTuple):
    reports: List[LiquidityPoolReport]
    charts: Dict[str, List[LPDailyGraphPoint]]


class AsgardConsumerConnectorBase:
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = class_logger(self)

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
    async def get_my_pools(self, address) -> List[str]:
        ...
