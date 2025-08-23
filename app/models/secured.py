from typing import NamedTuple, List, Optional, Dict


class SecureAssetInfo(NamedTuple):
    asset: str
    supply: float
    price_usd: float
    value_usd: float
    holders: int
    to_pool_depth_ratio: float
    pool_depth: float
    l1_name: str
    display_name: str
    volume_24h_usd: float

    @property
    def secured_to_pool_percentage(self) -> float:
        if self.pool_depth == 0:
            return 0.0
        return (self.supply / self.pool_depth) * 100.0


class SecuredAssetsStats(NamedTuple):
    asset_names_sorted: List[str]
    assets: Dict[str, SecureAssetInfo]
    total_vault_usd: float
    total_pool_usd: float
    total_volume_24h_usd: float = 0.0

    @property
    def total_assets(self) -> int:
        return len(self.assets)

    @property
    def total_value_usd(self) -> float:
        return sum(asset.value_usd for asset in self.assets.values())

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
