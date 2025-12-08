from collections import defaultdict
from typing import List

from api.aionode.types import ThorVault, thor_to_float
from jobs.fetch.base import BaseFetcher
from lib.cache import async_cache
from lib.depcont import DepContainer
from models.asset import Asset
from models.price import PriceHolder
from models.secured import SecuredAssetsStats, SecureAssetInfo, AlertSecuredAssetSummary


# This fetcher loads secured asset data for current and previous epochs
class SecuredAssetAssetFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        sleep_period = deps.cfg.as_interval("secured_assets.period", "10m")
        super().__init__(deps, sleep_period=sleep_period)
        self.delta_period = deps.cfg.as_interval("secured_assets.delta_period", "1d")

    async def load_asgard_assets(self, height=0):
        asgards = await self.deps.thor_connector.query_vault(ThorVault.TYPE_ASGARD, height)
        results = defaultdict(float)

        for asgard in asgards:
            for coin in asgard.coins:
                results[coin.asset] += thor_to_float(coin.amount)

        return results

    @async_cache(ttl=40)
    async def load_volumes_usd_prev_curr(self, pool, days=1):
        swap_stats = await self.deps.midgard_connector.query_swap_stats(count=days * 2 + 1, interval='day', pool=pool)
        swap_stats = swap_stats.with_last_day_dropped
        start_day = 1 if len(swap_stats.intervals) % 2 else 0

        previous_volume = sum(it.from_secured_volume_usd + it.to_secured_volume_usd
                              for it in swap_stats.intervals[start_day:days])
        current_volume = sum(it.from_secured_volume_usd + it.to_secured_volume_usd
                             for it in swap_stats.intervals[days:])

        # s = swap_stats.meta.from_trade_volume_usd + swap_stats.meta.to_trade_volume_usd
        return previous_volume, current_volume

    def get_total_vaults_usd(self, asgards: List[ThorVault], ph: PriceHolder):
        total_vault_usd = 0.0
        for asgard in asgards:
            for coin in asgard.coins:
                price = ph.get_asset_price_in_usd(coin.asset)
                if price:
                    total_vault_usd += thor_to_float(coin.amount) * price
                else:
                    self.logger.debug(f"coin {coin.asset} has no price")
        return total_vault_usd

    async def load_holders(self, asset: str, height=None):
        holders = await self.deps.thor_connector.query_holders(asset, height)
        return len(holders) if holders else 0

    async def load_supply(self, height=None):
        return await self.deps.thor_connector.query_secured_assets(height)

    async def load_epoch(self, *, current=False, previous=False):
        assert current or previous
        ph = await self.deps.pool_cache.get()
        if not ph or not ph.pool_info_map:
            self.logger.error("No pools found")
            return

        height = None if current else await self.deps.last_block_cache.get_thor_block_time_ago(self.delta_period)

        asgards = await self.deps.thor_connector.query_vault(ThorVault.TYPE_ASGARD, height)
        supply_now = await self.load_supply(height)

        total_volume_usd = 0.0
        assets = []
        for secured_asset in supply_now:
            supply = thor_to_float(secured_asset.supply)
            name = secured_asset.asset
            price = ph.get_asset_price_in_usd(name) or 0.0
            pool = ph.pool_fuzzy_first(name)
            pool = ph.find_pool(pool) if pool else None
            pool_depth = thor_to_float(pool.balance_asset) if pool else 0
            to_pool_depth_ratio = supply / pool_depth if pool_depth > 0 else 0.0
            holders = await self.load_holders(name, height=height)
            a = Asset(name).l1_asset
            volume_24h_prev, volume_24h_curr = await self.load_volumes_usd_prev_curr(str(a), days=1) if pool else (0, 0)
            volume = volume_24h_prev if height else volume_24h_curr
            total_volume_usd += volume
            assets.append(SecureAssetInfo(
                name,
                supply=supply,
                price_usd=price,
                value_usd=supply * price,
                holders=holders,
                to_pool_depth_ratio=to_pool_depth_ratio,
                pool_depth=pool_depth,
                l1_name=str(a),
                display_name=a.pretty_str,
                volume_24h_usd=volume,
            ))

        total_vault_usd = self.get_total_vaults_usd(asgards, ph)
        total_pool_usd = ph.total_pooled_value_usd * 0.5  # non-Rune assets are half of the total pool value

        assets.sort(key=lambda a: a.value_usd, reverse=True)
        asset_names_sorted = [asset.l1_name for asset in assets]
        asset_dict = {asset.l1_name: asset for asset in assets}

        return SecuredAssetsStats(
            assets=asset_dict,
            asset_names_sorted=asset_names_sorted,
            total_pool_usd=total_pool_usd,
            total_vault_usd=total_vault_usd,
            total_volume_24h_usd=total_volume_usd,
        )

    async def fetch(self) -> AlertSecuredAssetSummary:
        current = await self.load_epoch(current=True)
        previous = await self.load_epoch(previous=True)

        if previous is None:
            previous = current

        return AlertSecuredAssetSummary(
            current=current,
            previous=previous,
            period_seconds=self.delta_period,
        )
