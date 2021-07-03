import logging
import time
from dataclasses import dataclass
from typing import List

from services.lib.constants import BNB_BTCB_SYMBOL, BTC_SYMBOL, STABLE_COIN_POOLS, THOR_DIVIDER_INV
from services.lib.money import weighted_mean
from services.models.base import BaseModelMixin
from services.models.pool_info import PoolInfo, PoolInfoMap


@dataclass
class RuneMarketInfo:
    circulating: int = 500_000_000
    rune_vault_locked: int = 0
    real_rune_price: float = 0.0  # THORChain Pool Price (weighted across stable coins)
    fair_price: float = 0.0  # Deterministic Price
    cex_price: float = 0.0  # Price on Centralised Exchanges
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
    fair_price: RuneMarketInfo = RuneMarketInfo()
    last_ath: PriceATH = PriceATH()
    btc_real_rune_price: float = 0.0


class LastPriceHolder:
    def __init__(self):
        self.usd_per_rune = 1.0  # weighted across multiple stable coin pools
        self.btc_per_rune = 0.000001
        self.pool_info_map: PoolInfoMap = {}
        self.last_update_ts = 0

    def _calculate_weighted_rune_price(self):
        prices, weights = [], []
        for stable_symbol in STABLE_COIN_POOLS:
            pool_info = self.pool_info_map.get(stable_symbol)
            if pool_info and pool_info.balance_rune > 0 and pool_info.asset_per_rune > 0:
                prices.append(pool_info.asset_per_rune)
                weights.append(pool_info.balance_rune)

        if prices:
            self.usd_per_rune = weighted_mean(prices, weights)
        else:
            logging.error(f'LastPriceHolder was unable to find any stable coin pools!')

    def _calculate_btc_price(self):
        self.btc_per_rune = 0.0
        btc_symbols = (BTC_SYMBOL, BNB_BTCB_SYMBOL)
        for btc_symbol in btc_symbols:
            pool = self.pool_info_map.get(btc_symbol)
            if pool is not None:
                self.btc_per_rune = pool.asset_per_rune
                return

    def update(self, new_pool_info_map: PoolInfoMap):
        self.pool_info_map = new_pool_info_map.copy()
        self._calculate_weighted_rune_price()
        self._calculate_btc_price()
        self.last_update_ts = time.time()

    @property
    def pool_names(self):
        return set(self.pool_info_map.keys())

    def usd_per_asset(self, pool):
        runes_per_asset = self.pool_info_map[pool].runes_per_asset
        return self.usd_per_rune * runes_per_asset

    def find_pool(self, asset):
        return self.pool_info_map.get(asset)

    @property
    def total_locked_value_usd(self):
        tlv = 0  # in USD
        for pool in self.pool_info_map.values():
            pool: PoolInfo
            tlv += (pool.balance_rune * THOR_DIVIDER_INV) * self.usd_per_rune
        return tlv

    def pool_fuzzy_search(self, query: str) -> List[str]:
        if not query:
            return []

        query = query.upper()
        pool_names = self.pool_names
        if query in pool_names:  # perfect match
            return [query]

        variants = []
        for pool_name in pool_names:
            if query in pool_name:
                variants.append(pool_name)
        return variants

