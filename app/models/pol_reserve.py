import dataclasses
from dataclasses import dataclass, field
from typing import List, Optional, Dict

from lib.constants import thor_to_float, THOR_BASIS_POINT_MAX
from lib.date_utils import DAY, YEAR
from models.asset import Asset


@dataclass
class PolReservePoolSnapshot:
    """
    The pol_reserve module's position in one pool at some block height.
    All amounts are raw (1e8) integers as THORNode returns them.
    """
    asset: str
    rune_deposited: int  # cumulative RUNE deployed into the pool
    units: int  # LP units of the module
    pool_units: int  # total pool units, synth units included
    balance_rune: int
    balance_asset: int
    status: str = ''

    @property
    def share(self) -> float:
        """Fraction (0..1) of the pool that the module owns"""
        return self.units / self.pool_units if self.pool_units else 0.0

    @property
    def share_percent(self) -> float:
        return self.share * 100.0

    @property
    def deeper_percent(self) -> Optional[float]:
        """How much deeper the pool is compared to the same pool without the POL position"""
        share = self.share
        return share / (1.0 - share) * 100.0 if 0.0 <= share < 1.0 else None

    @property
    def rune_deposited_float(self) -> float:
        return thor_to_float(self.rune_deposited)

    @property
    def rune_held(self) -> float:
        return thor_to_float(self.balance_rune) * self.share

    @property
    def asset_held(self) -> float:
        return thor_to_float(self.balance_asset) * self.share

    @property
    def value_rune(self) -> float:
        # both sides of a pool position are worth the same at the pool price
        return self.rune_held * 2.0

    @property
    def pnl_rune(self) -> float:
        return self.value_rune - self.rune_deposited_float

    @property
    def pnl_percent(self) -> float:
        deposited = self.rune_deposited_float
        return self.pnl_rune / deposited * 100.0 if deposited else 0.0

    def to_dict(self):
        return dataclasses.asdict(self)

    @classmethod
    def from_json(cls, j):
        return cls(
            asset=j.get('asset', ''),
            rune_deposited=int(j.get('rune_deposited', 0)),
            units=int(j.get('units', 0)),
            pool_units=int(j.get('pool_units', 0)),
            balance_rune=int(j.get('balance_rune', 0)),
            balance_asset=int(j.get('balance_asset', 0)),
            status=j.get('status', ''),
        )


@dataclass
class PolReserveSnapshot:
    """All positions of the pol_reserve module at some block height"""
    height: int
    timestamp: int
    pools: List[PolReservePoolSnapshot] = field(default_factory=list)
    undeployed_rune: int = 0  # RUNE waiting in the module, raw (1e8)
    usd_per_rune: float = 0.0

    def find_pool(self, asset: str) -> Optional[PolReservePoolSnapshot]:
        return next((p for p in self.pools if p.asset == asset), None)

    @property
    def rune_deposited(self) -> float:
        return sum(p.rune_deposited_float for p in self.pools)

    @property
    def rune_held(self) -> float:
        return sum(p.rune_held for p in self.pools)

    @property
    def value_rune(self) -> float:
        return sum(p.value_rune for p in self.pools)

    @property
    def value_usd(self) -> float:
        return self.value_rune * self.usd_per_rune

    @property
    def pnl_rune(self) -> float:
        return self.value_rune - self.rune_deposited

    @property
    def pnl_percent(self) -> float:
        deposited = self.rune_deposited
        return self.pnl_rune / deposited * 100.0 if deposited else 0.0

    @property
    def active_pool_count(self) -> int:
        return sum(1 for p in self.pools if p.units > 0)

    @property
    def is_zero(self) -> bool:
        return not any(p.rune_deposited or p.units for p in self.pools)

    def to_dict(self):
        return dataclasses.asdict(self)

    @classmethod
    def from_json(cls, j):
        return cls(
            height=int(j.get('height', 0)),
            timestamp=int(j.get('timestamp', 0)),
            pools=[PolReservePoolSnapshot.from_json(p) for p in j.get('pools') or []],
            undeployed_rune=int(j.get('undeployed_rune', 0)),
            usd_per_rune=float(j.get('usd_per_rune', 0.0)),
        )


@dataclass
class PolReserveDay:
    """What happened with the pol_reserve positions during one UTC day"""
    date: str  # YYYY-MM-DD
    timestamp: int  # start of the day
    deposited_rune: float = 0.0
    deposited_by_pool: Dict[str, float] = field(default_factory=dict)
    cumulative_deposited_rune: float = 0.0
    value_rune: float = 0.0  # position value at the end of the day
    avg_value_rune: float = 0.0  # mean of the values at the start and at the end of the day
    usd_per_rune: float = 0.0  # Midgard price at the end of the day
    system_income_rune: float = 0.0
    fees_rune: float = 0.0  # swap fees of the pools times the POL share (gross, goes to system income)
    earnings_rune: float = 0.0  # pool earnings times the POL share (what the LP position really gets)
    partial: bool = False  # the day is not over yet

    @property
    def deposited_usd(self) -> float:
        return self.deposited_rune * self.usd_per_rune

    @property
    def value_usd(self) -> float:
        return self.value_rune * self.usd_per_rune

    @property
    def fees_usd(self) -> float:
        return self.fees_rune * self.usd_per_rune

    @property
    def earnings_usd(self) -> float:
        return self.earnings_rune * self.usd_per_rune


def build_pol_reserve_day(
        date: str,
        timestamp: int,
        start: Optional[PolReserveSnapshot],
        end: PolReserveSnapshot,
        cumulative_before: float = 0.0,
        usd_per_rune: float = 0.0,
        system_income_rune: float = 0.0,
        pool_fees_rune: Optional[Dict[str, float]] = None,
        pool_earnings_rune: Optional[Dict[str, float]] = None,
        partial: bool = False,
) -> PolReserveDay:
    """
    Compares the snapshots at the start and at the end of a day.
    Fees and earnings of every pool are attributed to POL by its mean share over the day.
    """
    pool_fees_rune = pool_fees_rune or {}
    pool_earnings_rune = pool_earnings_rune or {}

    deposited_by_pool = {}
    fees = earnings = 0.0
    for pool in end.pools:
        before = start.find_pool(pool.asset) if start else None
        delta = pool.rune_deposited_float - (before.rune_deposited_float if before else 0.0)
        if delta > 0:
            deposited_by_pool[pool.asset] = delta

        avg_share = (pool.share + (before.share if before else 0.0)) / 2.0
        fees += pool_fees_rune.get(pool.asset, 0.0) * avg_share
        earnings += pool_earnings_rune.get(pool.asset, 0.0) * avg_share

    deposited = sum(deposited_by_pool.values())
    start_value = start.value_rune if start else 0.0
    return PolReserveDay(
        date=date,
        timestamp=timestamp,
        deposited_rune=deposited,
        deposited_by_pool=deposited_by_pool,
        cumulative_deposited_rune=cumulative_before + deposited,
        value_rune=end.value_rune,
        avg_value_rune=(start_value + end.value_rune) / 2.0,
        usd_per_rune=usd_per_rune,
        system_income_rune=system_income_rune,
        fees_rune=fees,
        earnings_rune=earnings,
        partial=partial,
    )


@dataclass
class AlertPolReserveStats:
    current: PolReserveSnapshot
    days: List[PolReserveDay] = field(default_factory=list)  # oldest first, the last one may be partial
    previous: Optional[PolReserveSnapshot] = None  # at the moment of the previous alert
    system_income_bps: int = 0
    max_deployment_rune: float = 0.0  # per block
    module_address: str = ''
    chart_days: int = 30  # how many of the last days go to the infographic chart

    @property
    def usd_per_rune(self) -> float:
        return self.current.usd_per_rune

    @property
    def system_income_percent(self) -> float:
        return self.system_income_bps / THOR_BASIS_POINT_MAX * 100.0

    @property
    def complete_days(self) -> List[PolReserveDay]:
        return [d for d in self.days if not d.partial]

    def last_days(self, n: int) -> List[PolReserveDay]:
        return self.complete_days[-n:] if n > 0 else []

    @property
    def avg_daily_deposit_rune(self) -> float:
        days = self.complete_days
        return sum(d.deposited_rune for d in days) / len(days) if days else 0.0

    @property
    def deposited_usd_at_cost(self) -> float:
        """USD value of the deposits at the prices of the days they were made"""
        return sum(d.deposited_usd for d in self.days)

    def fees_rune(self, n_days: int = 0, net: bool = False) -> float:
        """Estimated fees over the last n complete days (all known days when n_days == 0)"""
        days = self.last_days(n_days) if n_days else self.days
        return sum((d.earnings_rune if net else d.fees_rune) for d in days)

    def fees_usd(self, n_days: int = 0, net: bool = False) -> float:
        days = self.last_days(n_days) if n_days else self.days
        return sum((d.earnings_usd if net else d.fees_usd) for d in days)

    def apr_percent(self, n_days: int, net: bool = False) -> Optional[float]:
        """Fees over the last n complete days against the mean position value, annualized, not compounded"""
        days = self.last_days(n_days)
        value_days = sum(d.avg_value_rune for d in days)
        if not days or value_days <= 0:
            return None
        fees = sum((d.earnings_rune if net else d.fees_rune) for d in days)
        return fees / value_days * (YEAR / DAY) * 100.0

    @property
    def value_change_percent(self) -> Optional[float]:
        """Change of the position value in RUNE since the previous alert"""
        if not self.previous or not self.previous.value_rune:
            return None
        return (self.current.value_rune / self.previous.value_rune - 1.0) * 100.0

    @property
    def pnl_usd(self) -> float:
        """Current USD value against the USD value of the deposits on the days they were made"""
        return self.current.value_usd - self.deposited_usd_at_cost

    @property
    def pnl_usd_percent(self) -> float:
        cost = self.deposited_usd_at_cost
        return self.pnl_usd / cost * 100.0 if cost else 0.0

    def _fees_dict(self, net: bool):
        return {
            'rune': self.fees_rune(net=net),
            'usd': self.fees_usd(net=net),
            'apr_7d': self.apr_percent(7, net=net),
            'apr_30d': self.apr_percent(30, net=net),
        }

    def to_dict(self):
        """Parameters of the infographic template"""
        cur, prev = self.current, self.previous
        usd_per_rune = self.usd_per_rune
        complete = self.complete_days
        chart = self.days[-self.chart_days:] if self.chart_days > 0 else []
        peak = max(complete, key=lambda d: d.deposited_rune, default=None)

        pools = []
        for p in cur.pools:
            asset = Asset.from_string(p.asset)
            pools.append({
                'asset': p.asset,
                'name': asset.pretty_str_no_emoji,
                'ticker': asset.name,
                'status': p.status,
                'share_percent': p.share_percent,
                'deeper_percent': p.deeper_percent,
                'rune_deposited': p.rune_deposited_float,
                'rune_held': p.rune_held,
                'asset_held': p.asset_held,
                'value_rune': p.value_rune,
                'value_usd': p.value_rune * usd_per_rune,
                'pnl_percent': p.pnl_percent,
            })

        return {
            'usd_per_rune': usd_per_rune,
            'system_income_percent': self.system_income_percent,
            'max_deployment_rune': self.max_deployment_rune,
            'module_address': self.module_address,
            'start_date': self.days[0].date if self.days else '',
            'end_date': self.days[-1].date if self.days else '',
            'total_days': len(self.days),
            'current': {
                'height': cur.height,
                'timestamp': cur.timestamp,
                'value_rune': cur.value_rune,
                'value_usd': cur.value_usd,
                'rune_deposited': cur.rune_deposited,
                'deposited_usd_at_cost': self.deposited_usd_at_cost,
                'rune_held': cur.rune_held,
                'assets_value_rune': cur.value_rune - cur.rune_held,
                'undeployed_rune': thor_to_float(cur.undeployed_rune),
                'pool_count': cur.active_pool_count,
                'pnl_rune': cur.pnl_rune,
                'pnl_rune_percent': cur.pnl_percent,
                'pnl_usd': self.pnl_usd,
                'pnl_usd_percent': self.pnl_usd_percent,
            },
            'previous': {
                'timestamp': prev.timestamp,
                'value_rune': prev.value_rune,
                'value_usd': prev.value_usd,
                'rune_deposited': prev.rune_deposited,
            } if prev else None,
            'pools': pools,
            'deposits': {
                'avg_daily_rune': self.avg_daily_deposit_rune,
                'peak_rune': peak.deposited_rune if peak else 0.0,
                'peak_date': peak.date if peak else '',
                'last_day_rune': complete[-1].deposited_rune if complete else 0.0,
                'last_7d_rune': sum(d.deposited_rune for d in complete[-7:]),
            },
            'fees': {
                # swap fees of the pools by the POL share: most of them go to system income
                'gross': self._fees_dict(net=False),
                # what the LP position itself earns
                'net': self._fees_dict(net=True),
            },
            'chart_days': len(chart),
            'daily': [
                {
                    'date': d.date,
                    'partial': d.partial,
                    'deposited_rune': d.deposited_rune,
                    'deposited_usd': d.deposited_usd,
                    'deposited_by_pool': d.deposited_by_pool,
                    'cumulative_deposited_rune': d.cumulative_deposited_rune,
                    'value_rune': d.value_rune,
                    'value_usd': d.value_usd,
                    'fees_rune': d.fees_rune,
                    'earnings_rune': d.earnings_rune,
                } for d in chart
            ],
        }
