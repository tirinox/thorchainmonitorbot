from typing import NamedTuple, List, Optional


class SecureAssetInfo(NamedTuple):
    asset: str
    supply: float
    price_usd: float
    total_value_usd: float
    holders: int
    to_pool_depth_ratio: float
    pool_depth: float


class SecuredAssetsStats(NamedTuple):
    assets: List[SecureAssetInfo]
    total_vault_usd: float
    total_pool_usd: float

    @property
    def total_assets(self) -> int:
        return len(self.assets)

    @property
    def total_value_usd(self) -> float:
        return sum(asset.total_value_usd for asset in self.assets)

    @property
    def total_secured_to_pool_percentage(self) -> float:
        if self.total_pool_usd == 0:
            return 0.0
        return (self.total_value_usd / self.total_pool_usd) * 100.0

    @property
    def total_vault_to_pool_percentage(self) -> float:
        if self.total_pool_usd == 0:
            return 0.0
        return (self.total_vault_usd / self.total_pool_usd) * 100.0


class AlertSecuredAssetSummary(NamedTuple):
    period_seconds: int
    current: SecuredAssetsStats
    previous: Optional[SecuredAssetsStats] = None
