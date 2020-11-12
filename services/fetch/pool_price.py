import logging
from dataclasses import dataclass

import aiohttp

from services.config import Config
from services.db import DB
from services.fetch.base import BaseFetcher, INotified
from services.fetch.node_ip_manager import ThorNodeAddressManager

MIDGARD_MULT = 10 ** -8

BNB_SYMBOL = 'BNB.BNB'
BUSD_SYMBOL = 'BNB.BUSD-BD1'
RUNE_SYMBOL = 'BNB.RUNE-B1A'


@dataclass
class PoolInfo:
    asset: str
    price: float  # runes per 1 asset

    balance_asset: int
    balance_rune: int

    enabled: bool

    @classmethod
    def dummy(cls):
        return cls('', 1, 1, 1, False)

    @classmethod
    def from_dict(cls, j):
        balance_asset = int(j['balance_asset'])
        balance_rune = int(j['balance_rune'])
        return cls(asset=j['asset'],
                   price=(balance_asset / balance_rune),
                   balance_asset=balance_asset,
                   balance_rune=balance_rune,
                   enabled=(j['status'] == 'Enabled'))

    @property
    def to_dict(self):
        return {
            'balance_asset': self.balance_asset,
            'balance_rune': self.balance_rune
        }


class PoolPriceFetcher(BaseFetcher):
    def __init__(self, cfg: Config, db: DB, thor_man: ThorNodeAddressManager = ThorNodeAddressManager.shared(),
                 session=None, delegate: INotified = None):
        super().__init__(cfg, db, session, delegate=delegate)
        self.thor_man = thor_man
        self.logger = logging.getLogger('PoolPriceFetcher')
        self.session = session
        self.last_rune_price_in_usd = 0.0

    async def fetch(self):
        price = await self.get_price_in_rune(BUSD_SYMBOL)
        if price > 0:
            self.last_rune_price_in_usd = price
        self.logger.info(f'fresh rune price is ${self.last_rune_price_in_usd:.3f}')

    async def fetch_pool_data_historic(self, asset, height=0) -> PoolInfo:
        if asset == RUNE_SYMBOL:
            return PoolInfo.dummy()

        base_url = await self.thor_man.select_node_url()

        url = f"{base_url}/thorchain/pool/{asset}?height={height}"

        async with self.session.get(url) as resp:
            j = await resp.json()
            return PoolInfo.from_dict(j)

    async def get_price_in_rune(self, asset, height=0):
        if asset == RUNE_SYMBOL:
            return 1.0
        asset_pool = await self.fetch_pool_data_historic(asset, height)
        asset_per_rune = asset_pool.balance_asset / asset_pool.balance_rune
        return asset_per_rune

    async def get_historical_price(self, asset, height=0):
        dollar_per_rune = await self.get_price_in_rune(BUSD_SYMBOL, height)
        asset_per_rune = await self.get_price_in_rune(asset, height)

        asset_price_in_usd = dollar_per_rune / asset_per_rune

        return dollar_per_rune, asset_price_in_usd

    async def get_current_pool_data_full(self):
        base_url = await self.thor_man.select_node_url()

        url = f"{base_url}/thorchain/pools"
        logging.info(f"loading pool data from {url}")
        async with self.session.get(url) as resp:
            pools_info = await resp.json()
            return {
                pool['asset']: PoolInfo.from_dict(pool) for pool in pools_info
            }

    async def get_prices_of(self, asset_list):
        pool_dict = await self.get_current_pool_data_full()
        return {
            asset: pool for asset, pool in pool_dict.items() if pool in asset_list
        }
