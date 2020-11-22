import time
from dataclasses import dataclass
from typing import Dict

from services.models.base import BaseModelMixin
from services.models.pool_info import PoolInfo
from services.lib.utils import Singleton
from services.models.time_series import BUSD_SYMBOL


@dataclass
class RuneFairPrice:
    circulating: int = 500_000_000
    rune_vault_locked: int = 0
    real_rune_price: float = 0.0
    fair_price: float = 0.0
    tlv_usd: float = 0.0
    rank: int = 0

    @property
    def market_cap(self):
        return self.real_rune_price * self.circulating


REAL_REGISTERED_ATH = 1.18  # BUSD / Rune
REAL_REGISTERED_ATH_DATE = 1598958000  # 1 sept 2020 11:00 UTC


@dataclass
class PriceATH(BaseModelMixin):
    ath_date: int = REAL_REGISTERED_ATH_DATE
    ath_price: float = REAL_REGISTERED_ATH

    def is_new_ath(self, price):
        return price and float(price) > 0 and float(price) > self.ath_price


@dataclass
class PriceReport:
    price_1h: float = 0.0
    price_24h: float = 0.0
    price_7d: float = 0.0
    fair_price: RuneFairPrice = RuneFairPrice()
    last_ath: PriceATH = PriceATH()


class LastPriceHolder(metaclass=Singleton):
    def __init__(self):
        self.usd_per_rune = 0.0
        self.pool_info_map: Dict[str, PoolInfo] = {}
        self.last_update_ts = 0

    def update(self, new_pool_info_map: Dict[str, PoolInfo]):
        self.pool_info_map = new_pool_info_map.copy()
        self.usd_per_rune = self.pool_info_map.get(BUSD_SYMBOL, PoolInfo.dummy()).asset_per_rune
        self.last_update_ts = time.time()

    @property
    def pool_names(self):
        return set(self.pool_info_map.keys())
