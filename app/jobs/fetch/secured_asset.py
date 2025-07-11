from collections import defaultdict
from typing import List

from api.aionode.types import ThorVault, thor_to_float
from jobs.fetch.base import BaseFetcher
from lib.depcont import DepContainer
from models.price import LastPriceHolder
from models.secured import SecuredAssetsStats, SecureAssetInfo


class SecuredAssetAssetFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        sleep_period = deps.cfg.as_interval("secured_assets.period", "10m")
        super().__init__(deps, sleep_period=sleep_period)

    async def load_asgard_assets(self, height=0):
        asgards = await self.deps.thor_connector.query_vault(ThorVault.TYPE_ASGARD, height)
        results = defaultdict(float)

        for asgard in asgards:
            for coin in asgard.coins:
                results[coin.asset] += thor_to_float(coin.amount)

        return results

    def get_total_vaults_usd(self, asgards: List[ThorVault], ph: LastPriceHolder):
        total_vault_usd = 0.0
        for asgard in asgards:
            for coin in asgard.coins:
                price = ph.get_asset_price_in_usd(coin.asset)
                if price:
                    total_vault_usd += thor_to_float(coin.amount) * price
                else:
                    self.logger.warning(f"coin {coin.asset} has no price")
        return total_vault_usd

    async def load_holders(self, asset: str, height=None):
        holders = await self.deps.thor_connector.query_holders(asset, height)
        return len(holders) if holders else 0

    async def load_for_height(self, height=0):
        ph = self.deps.price_holder
        if not ph.pool_info_map:
            self.logger.error("No pools found")
            return

        asgards = await self.deps.thor_connector.query_vault(ThorVault.TYPE_ASGARD, height)
        supply_now = await self.deps.thor_connector.query_secured_assets(height)

        assets = []
        for secured_asset in supply_now:
            supply = thor_to_float(secured_asset.supply)
            price = ph.get_asset_price_in_usd(secured_asset.asset) or 0.0
            pool = ph.pool_fuzzy_first(secured_asset.asset)
            pool = ph.find_pool(pool) if pool else None
            pool_depth = thor_to_float(pool.balance_asset) if pool else 0
            to_pool_depth_ratio = supply / pool_depth if pool_depth > 0 else 0.0
            holders = await self.load_holders(secured_asset.asset, height=height)
            assets.append(SecureAssetInfo(
                secured_asset.asset,
                supply=supply,
                price_usd=price,
                total_value_usd=supply * price,
                holders=holders,
                to_pool_depth_ratio=to_pool_depth_ratio,
                pool_depth=pool_depth
            ))

        total_vault_usd = self.get_total_vaults_usd(asgards, ph)
        total_pool_usd = ph.total_pooled_value_usd * 0.5  # non-Rune assets are half of the total pool value

        assets.sort(key=lambda a: a.total_value_usd, reverse=True)

        return SecuredAssetsStats(
            assets=assets,
            total_pool_usd=total_pool_usd,
            total_vault_usd=total_vault_usd,
        )

    async def fetch(self) -> SecuredAssetsStats:
        return await self.load_for_height()
