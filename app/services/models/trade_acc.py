from typing import NamedTuple, List, Optional

from aionode.types import ThorTradeUnits, ThorVault, ThorTradeAccount
from proto.access import NativeThorTx
from services.models.asset import ASSET_TRADE_SEPARATOR, ASSET_NORMAL_SEPARATOR, normalize_asset
from services.models.pool_info import PoolInfoMap


class AlertTradeAccountAction(NamedTuple):
    tx: NativeThorTx
    actor: str
    destination_address: str
    amount: float
    usd_amount: float
    asset: str
    is_deposit: bool
    chain: str
    wait_time: float = 0.0

    @property
    def is_withdrawal(self) -> bool:
        return not self.is_deposit


class TradeAccountSummary(NamedTuple):
    total_usd: float

    pool2acc: dict[str, ThorTradeUnits]
    pools: PoolInfoMap
    pool2traders: dict[str, List[ThorTradeAccount]]
    vault_balances: List[ThorVault]

    @classmethod
    def from_trade_units(cls, units: List[ThorTradeUnits],
                         pools: PoolInfoMap,
                         pool2traders: dict[str, List[ThorTradeAccount]],
                         vaults: List[ThorVault]):
        pool2acc = {}
        total_usd = 0.0
        for unit in units:
            pool = pools.get(normalize_asset(unit.asset))
            if pool:
                pool2acc[pool.asset] = unit
                total_usd += unit.depth_float * pool.usd_per_asset
        return cls(total_usd, pool2acc, pools, pool2traders, vaults)

    @property
    def total_traders(self) -> int:
        return sum(len(t) for t in self.pool2traders.values())

    def usd_units(self, asset) -> float:
        pool = self.pools.get(normalize_asset(asset))
        if pool:
            return self.pool2acc.get(pool.asset).depth_float * pool.usd_per_asset

    def top_by_usd_value(self, n: int) -> List[ThorTradeUnits]:
        try:
            return sorted(self.pool2acc.values(), key=lambda x: self.usd_units(x.asset), reverse=True)[:n]
        except (TypeError, ValueError):
            return []


class AlertTradeAccountSummary(NamedTuple):
    current: TradeAccountSummary
    previous: Optional[TradeAccountSummary]

    swaps_current: int = 0
    swaps_prev: int = 0

    swap_vol_current_usd: float = 0.0
    swap_vol_prev_usd: float = 0.0
