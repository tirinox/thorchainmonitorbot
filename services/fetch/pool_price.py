import logging
from dataclasses import dataclass

import aiohttp

from services.fetch.node_ip_manager import ThorNodeAddressManager


@dataclass
class PoolBalance:
    balance_asset: int
    balance_rune: int

    @classmethod
    def from_dict(cls, pool_data):
        return PoolBalance(int(pool_data['balance_asset']), int(pool_data['balance_rune']))

    @property
    def to_dict(self):
        return {
            'balance_asset': self.balance_asset,
            'balance_rune': self.balance_rune
        }


class PoolPriceFetcher:
    BUSD = 'BNB.BUSD-BD1'
    RUNE_SYMBOL = 'BNB.RUNE-B1A'

    def __init__(self, thor_man: ThorNodeAddressManager, session=None):
        self.thor_man = thor_man
        self.logger = logging.getLogger('PoolPriceFetcher')
        self.nodes_ip = []
        self._cnt = 0
        self.session = session or aiohttp.ClientSession()

    async def fetch_pool_data(self, asset, height=0) -> PoolBalance:
        if asset == self.RUNE_SYMBOL:
            return PoolBalance(1, 1)

        base_url = await self.thor_man.select_node_url()

        url = f"{base_url}/thorchain/pool/{asset}?height={height}"

        async with self.session.get(url) as resp:
            j = await resp.json()
            return PoolBalance.from_dict(j)

    async def get_price_in_rune(self, asset, height=0):
        if asset == self.RUNE_SYMBOL:
            return 1.0
        asset_pool = await self.fetch_pool_data(asset, height)
        asset_per_rune = asset_pool.balance_asset / asset_pool.balance_rune
        return asset_per_rune

    async def get_historical_price(self, asset, height=0):
        dollar_per_rune = await self.get_price_in_rune(self.BUSD, height)
        asset_per_rune = await self.get_price_in_rune(asset, height)

        asset_price_in_usd = dollar_per_rune / asset_per_rune

        return dollar_per_rune, asset_price_in_usd
