from typing import NamedTuple, List

from aionode.types import ThorTradeUnits, ThorVault, ThorTradeAccount
from proto.access import NativeThorTx
from services.models.pool_info import PoolInfoMap


class AlertTradeAccountAction(NamedTuple):
    tx: NativeThorTx
    actor: str
    destination_address: str
    amount: float
    usd_amount: float
    asset: str
    is_deposit: bool

    @property
    def is_withdraw(self) -> bool:
        return not self.is_deposit


class AlertTradeAccountSummary(NamedTuple):
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
            pool = pools.get(unit.asset)
            if pool:
                pool2acc[pool.asset] = unit
                total_usd += unit.depth_float * pool.usd_per_asset
        return cls(total_usd, pool2acc, pools, pool2traders, vaults)

    @property
    def total_traders(self) -> int:
        return sum(len(t) for t in self.pool2traders.values())

    def usd_units(self, asset) -> float:
        pool = self.pools.get(asset)
        if pool:
            return self.pool2acc.get(pool.asset).depth_float * pool.usd_per_asset
