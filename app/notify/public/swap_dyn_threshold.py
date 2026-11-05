import asyncio
import json
from dataclasses import dataclass, asdict
from typing import Optional

from lib.date_utils import now_ts, parse_timespan_to_seconds
from lib.db import DB
from lib.logs import WithLogger
from lib.money import parse_short_number
from models.asset import Asset

DB_KEY_SWAP_DYN_THRESHOLD = 'SwapDynThreshold'  # hash: direction -> BarRecord as JSON

# a bar below this is a cooled one: no longer shown, and the next swap starts a new series
COOLED_BAR_USD = 1.0


def swap_direction(in_asset: str, out_asset: str) -> str:
    """'BTC.BTC>ETH.ETH'; trade, secured and synth forms of an asset are the same direction as its L1 form"""
    return f'{Asset.to_L1_pool_name(in_asset)}>{Asset.to_L1_pool_name(out_asset)}'


@dataclass
class BarRecord:
    bar_usd: float  # the bar at `ts`; it falls with time, see DirectionalThreshold.bar_now
    ts: float
    count: int  # announced swaps in the current series
    last_volume_usd: float
    last_tx: str = ''


class DirectionalThreshold(WithLogger):
    """
    A bar a swap must clear on top of the static thresholds, one per swap direction.
    Every announced swap raises the bar of its direction to its volume x (1 + growth), so a series of equal
    swaps gives one message and only growing ones pass. The excess then halves every `half_life_sec`.
    """

    # ponytail: one lock per process; the bot is a single process. With several, use a Redis Lua script.
    _lock = asyncio.Lock()

    def __init__(self, db: DB, growth: float, half_life_sec: float, max_bar_usd: float, clock=now_ts):
        super().__init__()
        assert growth >= 0 and half_life_sec > 0 and max_bar_usd > 0
        self.db = db
        self.growth = growth
        self.half_life_sec = half_life_sec
        self.max_bar_usd = max_bar_usd
        self._clock = clock

    @classmethod
    def from_config(cls, db: DB, cfg) -> Optional['DirectionalThreshold']:
        """None when `tx.swap.dynamic_threshold.enabled` is off (the default)"""
        path = 'tx.swap.dynamic_threshold'
        if not cfg.as_bool(f'{path}.enabled', False):
            return None
        return cls(
            db,
            growth=cfg.as_float(f'{path}.growth', 0.4),
            half_life_sec=parse_timespan_to_seconds(cfg.as_str(f'{path}.half_life', '30m')),
            max_bar_usd=parse_short_number(cfg.as_str(f'{path}.max_bar_usd', '50M')),
        )

    def bar_now(self, rec: Optional[BarRecord]) -> float:
        if rec is None:
            return 0.0
        return rec.bar_usd * 0.5 ** (max(0.0, self._clock() - rec.ts) / self.half_life_sec)

    async def _load(self, direction: str) -> Optional[BarRecord]:
        redis = await self.db.get_redis()
        raw = await redis.hget(DB_KEY_SWAP_DYN_THRESHOLD, direction)
        return self._parse(raw)

    @staticmethod
    def _parse(raw) -> Optional[BarRecord]:
        try:
            return BarRecord(**json.loads(raw)) if raw else None
        except (TypeError, ValueError):
            return None

    async def current_bar(self, direction: str) -> float:
        return self.bar_now(await self._load(direction))

    async def passes(self, direction: str, volume_usd: float) -> bool:
        """Read only"""
        return volume_usd >= await self.current_bar(direction)

    async def check_and_record(self, direction: str, volume_usd: float, tx_id: str = '') -> bool:
        """Atomically: does the swap clear the bar? If so, it is announced, so the bar goes up."""
        async with self._lock:
            if not await self.passes(direction, volume_usd):
                self.logger.info(f'Swap {tx_id} {direction}: {volume_usd = :.0f} is below the dynamic bar')
                return False
            await self.record(direction, volume_usd, tx_id)
            return True

    async def record(self, direction: str, volume_usd: float, tx_id: str = ''):
        prev = await self._load(direction)
        bar = self.bar_now(prev)
        rec = BarRecord(
            bar_usd=min(max(bar, volume_usd) * (1 + self.growth), self.max_bar_usd),
            ts=self._clock(),
            count=(prev.count if prev and bar >= COOLED_BAR_USD else 0) + 1,
            last_volume_usd=volume_usd,
            last_tx=tx_id,
        )
        redis = await self.db.get_redis()
        await redis.hset(DB_KEY_SWAP_DYN_THRESHOLD, direction, json.dumps(asdict(rec)))
        self.logger.info(f'Dynamic bar of {direction}: {bar:.0f} -> {rec.bar_usd:.0f} (series of {rec.count})')

    async def snapshot(self) -> list[dict]:
        """Not cooled directions, the highest bar first"""
        redis = await self.db.get_redis()
        items = []
        for direction, raw in (await redis.hgetall(DB_KEY_SWAP_DYN_THRESHOLD)).items():
            if (rec := self._parse(raw)) and (bar := self.bar_now(rec)) >= COOLED_BAR_USD:
                items.append({'direction': direction, **asdict(rec), 'bar_usd': bar})
        return sorted(items, key=lambda x: x['bar_usd'], reverse=True)

    async def reset(self, direction: str) -> bool:
        redis = await self.db.get_redis()
        return bool(await redis.hdel(DB_KEY_SWAP_DYN_THRESHOLD, direction))

    async def reset_all(self) -> int:
        redis = await self.db.get_redis()
        directions = list(await redis.hgetall(DB_KEY_SWAP_DYN_THRESHOLD))
        return await redis.hdel(DB_KEY_SWAP_DYN_THRESHOLD, *directions) if directions else 0
