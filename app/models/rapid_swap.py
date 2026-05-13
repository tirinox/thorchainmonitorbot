from dataclasses import dataclass, field
from typing import List


@dataclass
class RapidSwapDelta:
    absolute: float = 0.0
    pct: float = 0.0


@dataclass
class RapidSwapTotals:
    rapid_swap_count: int = 0
    total_swap_count: int = 0
    unique_users: int = 0
    rapid_swap_volume_usd: float = 0.0
    rapid_swap_blocks_saved: int = 0
    rapid_swap_event_count: int = 0
    rapid_swap_share: float = 0.0
    estimated_time_saved_sec: float = 0.0
    avg_subswaps_per_tx: float = 0.0
    avg_faster_pct: float = 0.0
    efficiency_ratio: float = 0.0


@dataclass
class RapidSwapDeltas:
    rapid_swap_count: RapidSwapDelta = field(default_factory=RapidSwapDelta)
    rapid_swap_volume_usd: RapidSwapDelta = field(default_factory=RapidSwapDelta)
    unique_users: RapidSwapDelta = field(default_factory=RapidSwapDelta)
    estimated_time_saved_sec: RapidSwapDelta = field(default_factory=RapidSwapDelta)
    rapid_swap_share_pp: RapidSwapDelta = field(default_factory=RapidSwapDelta)


@dataclass
class RapidSwapDailyPoint:
    date: str = ''
    rapid_swap_count: int = 0
    total_swap_count: int = 0
    unique_users: int = 0
    rapid_swap_volume_usd: float = 0.0
    rapid_swap_blocks_saved: int = 0
    rapid_swap_event_count: int = 0
    rapid_swap_share: float = 0.0
    estimated_time_saved_sec: float = 0.0
    cumulative_rapid_swap_count: int = 0
    cumulative_rapid_swap_volume_usd: float = 0.0
    cumulative_estimated_time_saved_sec: float = 0.0
    cumulative_unique_users: int = 0
    avg_subswaps_per_tx: float = 0.0
    avg_faster_pct: float = 0.0


@dataclass
class RapidSwapTopPairStats:
    pair_label: str = ''
    rapid_swap_count: int = 0
    rapid_swap_volume_usd: float = 0.0
    avg_subswaps: float = 0.0
    avg_faster_pct: float = 0.0
    estimated_time_saved_sec: float = 0.0


@dataclass
class RapidSwapLargestSwap:
    when: str = ''
    tx_id: str = ''
    pair_label: str = ''
    trader: str = ''
    usd_volume: float = 0.0
    subswaps: int = 0
    blocks_used: int = 0
    blocks_saved: int = 0
    saved_time_sec: float = 0.0
    faster_pct: float = 0.0
    efficiency_ratio: float = 0.0


@dataclass
class RapidSwapPeriodStats:
    period_days: int = 7
    start_date: str = ''
    end_date: str = ''
    total: RapidSwapTotals = field(default_factory=RapidSwapTotals)
    previous: RapidSwapTotals = field(default_factory=RapidSwapTotals)
    delta: RapidSwapDeltas = field(default_factory=RapidSwapDeltas)
    daily: List[RapidSwapDailyPoint] = field(default_factory=list)
    top_pairs: List[RapidSwapTopPairStats] = field(default_factory=list)
    largest_swap: RapidSwapLargestSwap = field(default_factory=RapidSwapLargestSwap)

    def to_dict(self) -> dict:
        return {
            'period_days': self.period_days,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'total': {
                'rapid_swap_count': self.total.rapid_swap_count,
                'total_swap_count': self.total.total_swap_count,
                'unique_users': self.total.unique_users,
                'rapid_swap_volume_usd': self.total.rapid_swap_volume_usd,
                'rapid_swap_blocks_saved': self.total.rapid_swap_blocks_saved,
                'rapid_swap_event_count': self.total.rapid_swap_event_count,
                'rapid_swap_share': self.total.rapid_swap_share,
                'estimated_time_saved_sec': self.total.estimated_time_saved_sec,
                'avg_subswaps_per_tx': self.total.avg_subswaps_per_tx,
                'avg_faster_pct': self.total.avg_faster_pct,
                'efficiency_ratio': self.total.efficiency_ratio,
            },
            'previous': {
                'rapid_swap_count': self.previous.rapid_swap_count,
                'total_swap_count': self.previous.total_swap_count,
                'unique_users': self.previous.unique_users,
                'rapid_swap_volume_usd': self.previous.rapid_swap_volume_usd,
                'rapid_swap_blocks_saved': self.previous.rapid_swap_blocks_saved,
                'rapid_swap_event_count': self.previous.rapid_swap_event_count,
                'rapid_swap_share': self.previous.rapid_swap_share,
                'estimated_time_saved_sec': self.previous.estimated_time_saved_sec,
                'avg_subswaps_per_tx': self.previous.avg_subswaps_per_tx,
                'avg_faster_pct': self.previous.avg_faster_pct,
                'efficiency_ratio': self.previous.efficiency_ratio,
            },
            'delta': {
                'rapid_swap_count': {
                    'absolute': self.delta.rapid_swap_count.absolute,
                    'pct': self.delta.rapid_swap_count.pct,
                },
                'rapid_swap_volume_usd': {
                    'absolute': self.delta.rapid_swap_volume_usd.absolute,
                    'pct': self.delta.rapid_swap_volume_usd.pct,
                },
                'unique_users': {
                    'absolute': self.delta.unique_users.absolute,
                    'pct': self.delta.unique_users.pct,
                },
                'estimated_time_saved_sec': {
                    'absolute': self.delta.estimated_time_saved_sec.absolute,
                    'pct': self.delta.estimated_time_saved_sec.pct,
                },
                'rapid_swap_share_pp': {
                    'absolute': self.delta.rapid_swap_share_pp.absolute,
                    'pct': self.delta.rapid_swap_share_pp.pct,
                },
            },
            'daily': [
                {
                    'date': d.date,
                    'rapid_swap_count': d.rapid_swap_count,
                    'total_swap_count': d.total_swap_count,
                    'unique_users': d.unique_users,
                    'rapid_swap_volume_usd': d.rapid_swap_volume_usd,
                    'rapid_swap_blocks_saved': d.rapid_swap_blocks_saved,
                    'rapid_swap_event_count': d.rapid_swap_event_count,
                    'rapid_swap_share': d.rapid_swap_share,
                    'estimated_time_saved_sec': d.estimated_time_saved_sec,
                    'cumulative_rapid_swap_count': d.cumulative_rapid_swap_count,
                    'cumulative_rapid_swap_volume_usd': d.cumulative_rapid_swap_volume_usd,
                    'cumulative_estimated_time_saved_sec': d.cumulative_estimated_time_saved_sec,
                    'cumulative_unique_users': d.cumulative_unique_users,
                    'avg_subswaps_per_tx': d.avg_subswaps_per_tx,
                    'avg_faster_pct': d.avg_faster_pct,
                }
                for d in self.daily
            ],
            'top_pairs': [
                {
                    'pair_label': p.pair_label,
                    'rapid_swap_count': p.rapid_swap_count,
                    'rapid_swap_volume_usd': p.rapid_swap_volume_usd,
                    'avg_subswaps': p.avg_subswaps,
                    'avg_faster_pct': p.avg_faster_pct,
                    'estimated_time_saved_sec': p.estimated_time_saved_sec,
                }
                for p in self.top_pairs
            ],
            'largest_swap': {
                'when': self.largest_swap.when,
                'tx_id': self.largest_swap.tx_id,
                'pair_label': self.largest_swap.pair_label,
                'trader': self.largest_swap.trader,
                'usd_volume': self.largest_swap.usd_volume,
                'subswaps': self.largest_swap.subswaps,
                'blocks_used': self.largest_swap.blocks_used,
                'blocks_saved': self.largest_swap.blocks_saved,
                'saved_time_sec': self.largest_swap.saved_time_sec,
                'faster_pct': self.largest_swap.faster_pct,
                'efficiency_ratio': self.largest_swap.efficiency_ratio,
            },
        }

    def __repr__(self) -> str:
        return (
            f'RapidSwapPeriodStats('
            f'days={self.period_days}, '
            f'rapid_txs={self.total.rapid_swap_count}, '
            f'volume=${self.total.rapid_swap_volume_usd:,.0f}, '
            f'users={self.total.unique_users}, '
            f'saved={self.total.estimated_time_saved_sec:.0f}s)'
        )

