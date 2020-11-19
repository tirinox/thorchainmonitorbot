import time
from dataclasses import dataclass
from typing import Dict

from services.models.base import BaseModelMixin
from services.models.pool_info import PoolInfo
from services.utils import Singleton


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


class LastPriceHolder(metaclass=Singleton):
    def __init__(self):
        self.rune_price_in_usd = 0.0
        self.pool_info_map: Dict[str, PoolInfo] = {}
        self.last_update_ts = 0

    def update(self):
        self.last_update_ts = time.time()
