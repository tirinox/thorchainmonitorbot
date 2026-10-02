from datetime import datetime, timezone
from typing import NamedTuple, List, Optional

from api.aionode.types import ThorTradeUnits, ThorVault, ThorTradeAccount, float_to_thor
from lib.date_utils import now_ts, DAY
from .asset import normalize_asset, Asset
from .memo import ActionType
from .pool_info import PoolInfoMap
from .swap_history import SwapHistoryResponse
from .tx import ThorAction, SUCCESS, ThorSubTx, ThorCoin
from .vol_n import TxMetricType


class AlertTradeAccountAction(NamedTuple):
    tx_hash: str
    actor: str
    destination_address: str
    amount: float
    usd_amount: float
    asset: str
    is_deposit: bool
    chain: str
    wait_time: float = 0.0
    height: int = 0

    @property
    def is_withdrawal(self) -> bool:
        return not self.is_deposit

    @property
    def action_type(self) -> ActionType:
        return ActionType.TRADE_ACC_DEPOSIT if self.is_deposit else ActionType.TRADE_ACC_WITHDRAW

    @property
    def as_thor_tx(self) -> ThorAction:
        in_tx_list = []
        out_tx_list = []
        pools = [self.asset]

        # usd_per_asset = self.usd_amount / self.amount if self.amount > 0 else 0

        if self.is_deposit:
            in_tx_list.append(ThorSubTx(
                self.actor, [
                    ThorCoin(float_to_thor(self.amount), self.asset),
                ],
                self.tx_hash,
                height=self.height,
            ))
        else:
            out_tx_list.append(ThorSubTx(
                self.destination_address, [
                    ThorCoin(float_to_thor(self.amount), self.asset)
                ],
                self.tx_hash,
                height=self.height,
            ))

        ts = int(now_ts() * 1e9)
        return ThorAction(
            ts, 0, SUCCESS, self.action_type.value,
            pools, in_tx_list, out_tx_list,
            None, None, None, None,
            asset_amount=self.amount,
        )


class TradeAccountVaults(NamedTuple):
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

    @property
    def unique_traders(self) -> int:
        """One address holding several trade assets is counted once"""
        return len({t.owner for traders in self.pool2traders.values() for t in traders})

    def usd_units(self, asset) -> Optional[float]:
        pool = self.pools.get(normalize_asset(asset))
        # None for an asset that had no trade units at that moment, e.g. at the start of the period
        if pool and (unit := self.pool2acc.get(pool.asset)):
            return unit.depth_float * pool.usd_per_asset

    def top_by_usd_value(self, n: int) -> List[ThorTradeUnits]:
        try:
            return sorted(self.pool2acc.values(), key=lambda x: self.usd_units(x.asset), reverse=True)[:n]
        except (TypeError, ValueError):
            return []

    def holders_of(self, asset) -> int:
        return len(self.pool2traders.get(asset, []))

    def asset_rows(self, prev: Optional['TradeAccountVaults'] = None) -> List[dict]:
        """Every trade asset by its USD value, the largest first, for the infographic"""
        rows = []
        for unit in self.top_by_usd_value(len(self.pool2acc)):
            pool_name = self.pools[normalize_asset(unit.asset)].asset
            value_usd = self.usd_units(unit.asset) or 0.0
            prev_unit = prev.pool2acc.get(pool_name) if prev else None
            rows.append({
                'asset': unit.asset,
                'pool': pool_name,
                'name': Asset(pool_name).pretty_str,
                'amount': unit.depth_float,
                'value_usd': value_usd,
                'holders': self.holders_of(unit.asset),
                'share': value_usd / self.total_usd * 100.0 if self.total_usd else 0.0,
                'prev_amount': prev_unit.depth_float if prev_unit else None,
                'prev_value_usd': prev.usd_units(prev_unit.asset) if prev_unit else None,
                'prev_holders': prev.holders_of(prev_unit.asset) if prev_unit else None,
            })
        return rows


class TradeAccountStats(NamedTuple):
    tx_count: dict[str, int]
    tx_volume: dict[str, int]
    vaults: TradeAccountVaults

    @property
    def trade_swap_vol_usd(self):
        return self.tx_volume.get(TxMetricType.usd_key(TxMetricType.TRADE_SWAP), 0.0)

    @property
    def trade_swap_count(self):
        return self.tx_count.get(TxMetricType.TRADE_SWAP, 0)

    @property
    def trade_deposit_count(self):
        return self.tx_count.get(TxMetricType.TRADE_DEPOSIT, 0)

    @property
    def trade_withdrawal_count(self):
        return self.tx_count.get(TxMetricType.TRADE_WITHDRAWAL, 0)

    @property
    def trade_deposit_vol_usd(self):
        return self.tx_volume.get(TxMetricType.usd_key(TxMetricType.TRADE_DEPOSIT), 0.0)

    @property
    def trade_withdrawal_vol_usd(self):
        return self.tx_volume.get(TxMetricType.usd_key(TxMetricType.TRADE_WITHDRAWAL), 0.0)

    @property
    def all_swap_count(self):
        return self.tx_count.get(TxMetricType.SWAP, 0)

    def to_dict(self, trade_volume_usd: float, all_swap_volume_usd: float) -> dict:
        v = self.vaults
        return {
            # the vault fields are None when there was no snapshot of the vaults at the start of the period
            'value_usd': v.total_usd if v else None,
            'holders': v.total_traders if v else None,
            'unique_holders': v.unique_traders if v else None,
            'asset_count': len(v.pool2acc) if v else None,
            'trade_volume_usd': trade_volume_usd,
            'all_swap_volume_usd': all_swap_volume_usd,
            'swap_count': self.trade_swap_count,
            'all_swap_count': self.all_swap_count,
            'deposit_count': self.trade_deposit_count,
            'deposit_usd': self.trade_deposit_vol_usd,
            'withdrawal_count': self.trade_withdrawal_count,
            'withdrawal_usd': self.trade_withdrawal_vol_usd,
        }


class AlertTradeAccountStats(NamedTuple):
    curr: TradeAccountStats
    prev: TradeAccountStats
    swap_stats: SwapHistoryResponse
    period_sec: float = DAY
    # longer daily history from Midgard for the chart of the infographic
    daily_history: Optional[SwapHistoryResponse] = None
    chart_days: int = 14

    @property
    def curr_and_prev_trade_volume_usd(self):
        curr_to_trade, prev_to_trade = self.swap_stats.curr_and_prev_interval("to_trade_volume_usd")
        curr_from_trade, prev_from_trade = self.swap_stats.curr_and_prev_interval("from_trade_volume_usd")
        return (
            (curr_from_trade + curr_to_trade),
            (prev_from_trade + prev_to_trade)
        )

    @property
    def curr_and_prev_all_swap_volume_usd(self):
        return self.swap_stats.curr_and_prev_interval("total_volume_usd")

    def daily_rows(self) -> List[dict]:
        if not self.daily_history or not self.daily_history.intervals:
            return []
        return [
            {
                'date': datetime.fromtimestamp(day.start_time, tz=timezone.utc).date().isoformat(),
                'trade_volume_usd': day.to_trade_volume_usd + day.from_trade_volume_usd,
                'all_swap_volume_usd': day.total_volume_usd,
                'trade_swap_count': day.to_trade_count + day.from_trade_count,
            }
            for day in self.daily_history.last_whole_intervals(self.chart_days)
        ]

    def to_dict(self) -> dict:
        """Plain JSON for the trade_asset_summary.jinja2 infographic"""
        curr_trade_vol, prev_trade_vol = self.curr_and_prev_trade_volume_usd
        curr_all_vol, prev_all_vol = self.curr_and_prev_all_swap_volume_usd
        prev_vaults = self.prev.vaults if self.prev else None
        return {
            'period_seconds': self.period_sec,
            'period_days': max(1, round(self.period_sec / DAY)),
            'current': self.curr.to_dict(curr_trade_vol, curr_all_vol),
            'previous': self.prev.to_dict(prev_trade_vol, prev_all_vol) if self.prev else None,
            'assets': self.curr.vaults.asset_rows(prev_vaults),
            'daily': self.daily_rows(),
            'chart_days': self.chart_days,
        }
