import copy
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Set

from services.jobs.fetch.circulating import RuneCirculatingSupply
from services.lib.config import Config
from services.lib.constants import BTC_SYMBOL, STABLE_COIN_POOLS, thor_to_float, RUNE_IDEAL_SUPPLY
from services.lib.date_utils import now_ts, DAY
from services.lib.money import weighted_mean
from services.lib.texts import fuzzy_search
from services.models.asset import Asset, is_rune, ASSET_TRADE_SEPARATOR, ASSET_SYNTH_SEPARATOR, ASSET_NORMAL_SEPARATOR, \
    normalize_asset
from services.models.base import BaseModelMixin
from services.models.pool_info import PoolInfo, PoolInfoMap


@dataclass
class RuneMarketInfo:
    circulating: int = RUNE_IDEAL_SUPPLY
    rune_vault_locked: int = 0
    pool_rune_price: float = 0.0  # THORChain Pool Price (weighted across stable coins)
    fair_price: float = 0.0  # Deterministic Price
    cex_price: float = 0.0  # Price on Centralised Exchanges
    tlv_usd: float = 0.0
    rank: int = 0
    total_trade_volume_usd: float = 0.0
    total_supply: int = RUNE_IDEAL_SUPPLY
    supply_info: RuneCirculatingSupply = RuneCirculatingSupply.zero()
    pools: PoolInfoMap = None

    @property
    def market_cap(self):
        return self.pool_rune_price * self.circulating

    @property
    def is_valid(self):
        return (self.circulating > 0
                and self.fair_price > 0
                and self.cex_price > 0
                and self.pool_rune_price > 0
                and self.pools
                and self.supply_info
                and self.supply_info.total > 0
                )

    @property
    def divergence_percent(self):
        if self.pool_rune_price == 0:
            return 0.0
        return 100.0 * abs(1.0 - self.cex_price / self.pool_rune_price)

    @property
    def divergence(self):
        return self.cex_price - self.pool_rune_price

    @property
    def divergence_abs(self):
        return abs(self.cex_price - self.pool_rune_price)

    @property
    def total_pools(self):
        return len(self.pools)

    @property
    def total_active_pools(self):
        return len([p for p in self.pools.values() if p.is_enabled])


REAL_REGISTERED_ATH = 20.87  # $ / Rune
REAL_REGISTERED_ATH_DATE = 1621418550  # 19 may 2021


@dataclass
class PriceATH(BaseModelMixin):
    ath_date: int = REAL_REGISTERED_ATH_DATE
    ath_price: float = REAL_REGISTERED_ATH

    def is_new_ath(self, price):
        try:
            price = float(price)
        except TypeError:
            return False

        return price > REAL_REGISTERED_ATH and price > self.ath_price


@dataclass
class AlertPrice:
    price_1h: float = 0.0
    price_24h: float = 0.0
    price_7d: float = 0.0
    market_info: RuneMarketInfo = field(default_factory=RuneMarketInfo)
    last_ath: Optional[PriceATH] = None
    btc_pool_rune_price: float = 0.0
    is_ath: bool = False
    ath_sticker: str = ''
    halted_chains: Set[str] = None
    price_graph_period: int = 7 * DAY


class LastPriceHolder:
    def __init__(self, stable_coins=None):
        self.usd_per_rune = 1.0  # weighted across multiple stable coin pools
        self.btc_per_rune = 0.000001
        self.pool_info_map: PoolInfoMap = {}
        self.last_update_ts = 0
        self.stable_coins = stable_coins or STABLE_COIN_POOLS

    def clone(self):
        return copy.deepcopy(self)

    def is_stable_coin(self, c):
        return c in self.stable_coins

    def load_stable_coins(self, cfg: Config):
        self.stable_coins = cfg.get('thor.stable_coins', default=STABLE_COIN_POOLS)
        logging.info(f'Stable coins are {", ".join(self.stable_coins)}')

    def calculate_rune_price_here(self, pool_map: PoolInfoMap) -> float:
        return self.calculate_rune_price(self.stable_coins, pool_map)

    @staticmethod
    def calculate_rune_price(stable_coins, pool_map: PoolInfoMap) -> float:
        prices, weights = [], []
        stable_coins = stable_coins
        for stable_symbol in stable_coins:
            pool_info = pool_map.get(stable_symbol)
            if pool_info and pool_info.balance_rune > 0 and pool_info.asset_per_rune > 0:
                prices.append(pool_info.asset_per_rune)
                weights.append(pool_info.balance_rune)

        if prices:
            return weighted_mean(prices, weights)

    def _calculate_weighted_rune_price(self):
        usd_per_rune = self.calculate_rune_price_here(self.pool_info_map)

        if usd_per_rune:
            self.usd_per_rune = usd_per_rune
        else:
            logging.error(f'LastPriceHolder was unable to find any stable coin pools!')

    def _calculate_btc_price(self):
        self.btc_per_rune = 0.0
        btc_symbols = (BTC_SYMBOL,)
        for btc_symbol in btc_symbols:
            pool = self.pool_info_map.get(btc_symbol)
            if pool is not None:
                self.btc_per_rune = pool.asset_per_rune
                return

    def _fill_asset_price(self):
        if not self.usd_per_rune:
            logging.warning(f'Cannot fill asset_price_usd because {self.usd_per_rune = }')
            return
        for pool in self.pool_info_map.values():
            pool: PoolInfo
            pool.fill_usd_per_asset(self.usd_per_rune)

    def update(self, new_pool_info_map: PoolInfoMap):
        self.pool_info_map = new_pool_info_map.copy()
        self._calculate_weighted_rune_price()
        self._calculate_btc_price()
        self._fill_asset_price()
        self.last_update_ts = now_ts()
        return self

    @property
    def pool_names(self):
        return set(self.pool_info_map.keys())

    def usd_per_asset(self, pool):
        if pool in self.pool_info_map:
            runes_per_asset = self.pool_info_map[pool].runes_per_asset
            return self.usd_per_rune * runes_per_asset

    def find_pool(self, asset):
        return self.pool_info_map.get(asset)

    @property
    def total_pooled_value_usd(self):
        return self.total_pooled_value_rune * self.usd_per_rune

    @property
    def total_pooled_value_rune(self):
        tlv = 0
        for pool in self.pool_info_map.values():
            pool: PoolInfo
            tlv += thor_to_float(pool.balance_rune)
        return tlv * 2.0

    @staticmethod
    def restore_asset_type(original: str, name: str):
        if not name or not original:
            return name

        if ASSET_TRADE_SEPARATOR in original:
            return name.replace(ASSET_NORMAL_SEPARATOR, ASSET_TRADE_SEPARATOR, 1)
        elif ASSET_SYNTH_SEPARATOR in original:
            return name.replace(ASSET_NORMAL_SEPARATOR, ASSET_SYNTH_SEPARATOR, 1)
        else:
            return name

    def pool_fuzzy_search(self, query: str, restore_type=False) -> List[str]:
        if (q := query.lower()) in Asset.SHORT_NAMES:
            # See: https://dev.thorchain.org/thorchain-dev/concepts/memos#shortened-asset-names
            return [Asset.SHORT_NAMES[q]]
        results = fuzzy_search(query, self.pool_names)
        if restore_type:
            results = [self.restore_asset_type(query, r) for r in results]
        return results

    def pool_fuzzy_first(self, query: str, restore_type=False) -> str:
        original = query
        query = normalize_asset(query)

        # See: https://dev.thorchain.org/thorchain-dev/concepts/memos#asset-abbreviations
        candidates = self.pool_fuzzy_search(query)

        if not candidates:
            result = ''
        elif len(candidates) == 1:
            result = candidates[0]
        else:
            # If there are conflicts then the deepest pool is matched. (To prevent attacks).
            deepest_pool, deepest_rune = None, 0
            for candidate in candidates:
                pool = self.find_pool(candidate)
                if pool.balance_rune > deepest_rune:
                    deepest_rune = pool.balance_rune
                    deepest_pool = candidate

            result = deepest_pool

        return self.restore_asset_type(original, result) if restore_type else result

    def get_asset_price_in_rune(self, query: str):
        if is_rune(query):
            return 1.0
        full_name_of_asset = self.pool_fuzzy_first(query)
        pool = self.find_pool(full_name_of_asset)
        if pool:
            return pool.runes_per_asset

    def get_asset_price_in_usd(self, query: str):
        price_in_rune = self.get_asset_price_in_rune(query)
        if price_in_rune:
            return self.usd_per_rune * price_in_rune

    def convert_to_usd(self, amount: float, asset: str):
        price = self.get_asset_price_in_usd(asset)
        if price:
            return amount * price

    def total_synth_supply_in_usd(self):
        accum = 0.0
        for p in self.pool_info_map.values():
            if p.synth_supply:
                accum += p.synth_supply * p.usd_per_asset
        return accum

    @property
    def savers_pools(self):
        return [p.asset for p in self.pool_info_map.values() if p.savers_depth > 0]
