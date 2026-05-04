from dataclasses import dataclass, field
from typing import List


@dataclass
class LimitSwapDelta:
    """Absolute and percentage change between current and previous period."""
    absolute: float = 0.0
    pct: float = 0.0


@dataclass
class LimitSwapTotals:
    """Aggregated totals for a single period window."""
    opened_count: int = 0
    opened_usd: float = 0.0
    unique_traders: int = 0


@dataclass
class LimitSwapDeltas:
    """Per-metric deltas vs the previous equal-length period."""
    opened_count: LimitSwapDelta = field(default_factory=LimitSwapDelta)
    opened_usd: LimitSwapDelta = field(default_factory=LimitSwapDelta)
    unique_traders: LimitSwapDelta = field(default_factory=LimitSwapDelta)


@dataclass
class LimitSwapDailyPoint:
    """Metrics for a single calendar day (for chart rendering)."""
    date: str = ''
    opened_count: int = 0
    opened_usd: float = 0.0
    unique_traders: int = 0


@dataclass
class LimitSwapPairStats:
    """Stats for a single canonical trading pair."""
    pair: str = ''
    pair_label: str = ''
    opened_count: int = 0
    opened_usd: float = 0.0
    unique_traders: int = 0


@dataclass
class LimitSwapOpenState:
    """
    Live snapshot of currently open / queued limit swaps fetched directly
    from the THORNode API (query_limit_swaps_summary + query_limit_swaps_queue).
    """
    # From query_limit_swaps_summary
    total_count: int = 0          # total open limit swaps
    total_value_usd: float = 0.0  # combined USD value of all open orders
    oldest_swap_blocks: int = 0   # age of the oldest open order in blocks
    average_age_blocks: int = 0   # average age of open orders in blocks
    oldest_swap_duration: str = ''
    average_age_duration: str = ''
    # From query_limit_swaps_queue pagination
    queue_depth: int = 0          # live queue depth (may differ slightly from total_count)
    # Per-pair breakdown (from summary.asset_pairs)
    pairs: List[LimitSwapPairStats] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            'total_count': self.total_count,
            'total_value_usd': self.total_value_usd,
            'oldest_swap_blocks': self.oldest_swap_blocks,
            'average_age_blocks': self.average_age_blocks,
            'oldest_swap_duration': self.oldest_swap_duration,
            'average_age_duration': self.average_age_duration,
            'queue_depth': self.queue_depth,
            'pairs': [
                {
                    'pair': p.pair,
                    'pair_label': p.pair_label,
                    'opened_count': p.opened_count,
                    'opened_usd': p.opened_usd,
                    'unique_traders': p.unique_traders,
                }
                for p in self.pairs
            ],
        }


@dataclass
class LimitSwapPeriodStats:
    """
    Full stats snapshot for a rolling N-day window,
    ready for infographic generation and Telegram notification.
    """
    period_days: int = 7
    start_date: str = ''
    end_date: str = ''
    total: LimitSwapTotals = field(default_factory=LimitSwapTotals)
    previous: LimitSwapTotals = field(default_factory=LimitSwapTotals)
    delta: LimitSwapDeltas = field(default_factory=LimitSwapDeltas)
    daily: List[LimitSwapDailyPoint] = field(default_factory=list)
    top_pairs: List[LimitSwapPairStats] = field(default_factory=list)
    open_orders: LimitSwapOpenState = field(default_factory=LimitSwapOpenState)

    def to_dict(self) -> dict:
        """Serialize to a plain dict suitable for Jinja2 template rendering."""
        return {
            'period_days': self.period_days,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'total': {
                'opened_count': self.total.opened_count,
                'opened_usd': self.total.opened_usd,
                'unique_traders': self.total.unique_traders,
            },
            'previous': {
                'opened_count': self.previous.opened_count,
                'opened_usd': self.previous.opened_usd,
                'unique_traders': self.previous.unique_traders,
            },
            'delta': {
                'opened_count': {'absolute': self.delta.opened_count.absolute,
                                 'pct': self.delta.opened_count.pct},
                'opened_usd': {'absolute': self.delta.opened_usd.absolute,
                               'pct': self.delta.opened_usd.pct},
                'unique_traders': {'absolute': self.delta.unique_traders.absolute,
                                   'pct': self.delta.unique_traders.pct},
            },
            'daily': [
                {
                    'date': d.date,
                    'opened_count': d.opened_count,
                    'opened_usd': d.opened_usd,
                    'unique_traders': d.unique_traders,
                }
                for d in self.daily
            ],
            'top_pairs': [
                {
                    'pair': p.pair,
                    'pair_label': p.pair_label,
                    'opened_count': p.opened_count,
                    'opened_usd': p.opened_usd,
                    'unique_traders': p.unique_traders,
                }
                for p in self.top_pairs
            ],
            'open_orders': self.open_orders.to_dict(),
        }

    def __repr__(self) -> str:
        return (
            f'LimitSwapPeriodStats('
            f'days={self.period_days}, '
            f'orders={self.total.opened_count}, '
            f'volume=${self.total.opened_usd:,.0f}, '
            f'traders={self.total.unique_traders}, '
            f'open_now={self.open_orders.total_count})'
        )
