import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Tuple

from redis.asyncio import Redis

from api.midgard.parser import get_parser_by_network_id
from lib.constants import THOR_BLOCK_TIME
from lib.date_utils import date_parse_rfc
from lib.depcont import DepContainer
from lib.logs import WithLogger


@dataclass(frozen=True)
class Anchor:
    height: int
    ts: float  # Unix timestamp (seconds)


class DateToBlockMapper(WithLogger):
    """
    Fast approximate mapper: block height -> datetime/date

    - Anchors are stored every N blocks in Redis zset:
      score = block height, value = unix timestamp (as string)
    - Lookup uses nearest left/right anchors and linear interpolation
    - Anchors are created lazily via Tendermint block header queries
    """

    DB_KEY_BLOCK_TO_TS_ZSET = "Block2Ts:Thorchain:Anchors"  # zset: score=height, value=ts
    DB_KEY_ANCHOR_LOCK_PREFIX = "Block2Ts:Thorchain:lock"

    def __init__(self, deps: DepContainer, *, anchor_step: int = 2000):
        super().__init__()
        self.deps = deps
        self.midgard_parser = get_parser_by_network_id(deps.cfg.network_id)

        self.anchor_step = int(anchor_step)
        if self.anchor_step <= 0:
            raise ValueError("anchor_step must be > 0")

        # Use UTC datetimes for stable, unambiguous results
        self.use_utc = True

        # Lock bucket: prevent thundering herd for same anchor height
        self.lock_bucket_size = self.anchor_step

        self.max_anchor_span_blocks = self.anchor_step * 2
        self.max_time_drift_ratio = 0.1

        # ---------------------------------------------------------------------

    # Tendermint slow path
    # ---------------------------------------------------------------------

    async def get_last_thorchain_block(self) -> int:
        return await self.deps.last_block_cache.get_thor_block()

    async def get_timestamp_by_block_height_precise(self, block_height: int) -> float:
        """
        Returns -1 if the block is not available.
        """
        block_info = await self.deps.thor_connector.query_tendermint_block_raw(block_height)
        if not block_info or "result" not in block_info:
            return -1

        rfc_time = block_info["result"]["block"]["header"]["time"]
        dt = date_parse_rfc(rfc_time)
        return dt.timestamp()

    def _ts_to_datetime(self, ts: float) -> datetime:
        if self.use_utc:
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        return datetime.fromtimestamp(ts)

    # ---------------------------------------------------------------------
    # Redis helpers
    # ---------------------------------------------------------------------

    async def clear(self):
        r: Redis = await self.deps.db.get_redis()
        await r.delete(self.DB_KEY_BLOCK_TO_TS_ZSET)

    @asynccontextmanager
    async def _anchor_lock(self, bucket_key: str, ttl_sec: int = 30):
        """
        Distributed lock based on SET NX EX.
        """
        r: Redis = await self.deps.db.get_redis()
        lock_key = f"{self.DB_KEY_ANCHOR_LOCK_PREFIX}:{bucket_key}"
        acquired = await r.set(lock_key, "1", nx=True, ex=ttl_sec)
        try:
            yield bool(acquired)
        finally:
            if acquired:
                await r.delete(lock_key)

    async def _get_anchor_ts(self, height: int) -> Optional[float]:
        r: Redis = await self.deps.db.get_redis()
        # Get exact member by score using a narrow range query
        items = await r.zrangebyscore(self.DB_KEY_BLOCK_TO_TS_ZSET, min=height, max=height, start=0, num=1)
        if not items:
            return None
        return float(items[0])

    async def _save_anchor(self, height: int, ts: float):
        r: Redis = await self.deps.db.get_redis()
        await r.zadd(self.DB_KEY_BLOCK_TO_TS_ZSET, {str(float(ts)): int(height)})

    async def _get_neighbor_anchors(self, height: int) -> Tuple[Optional[Anchor], Optional[Anchor]]:
        """
        Returns (left_anchor, right_anchor).
        - left:  max anchor height <= height
        - right: min anchor height >= height
        """
        r: Redis = await self.deps.db.get_redis()

        # noinspection PyUnresolvedReferences
        left = await r.zrevrangebyscore(
            self.DB_KEY_BLOCK_TO_TS_ZSET,
            max=height,
            min="-inf",
            start=0,
            num=1,
            withscores=True,
        )
        right = await r.zrangebyscore(
            self.DB_KEY_BLOCK_TO_TS_ZSET,
            min=height,
            max="+inf",
            start=0,
            num=1,
            withscores=True,
        )

        left_anchor = None
        if left:
            val, score = left[0]  # val=str(ts), score=float(height)
            left_anchor = Anchor(height=int(score), ts=float(val))

        right_anchor = None
        if right:
            val, score = right[0]
            right_anchor = Anchor(height=int(score), ts=float(val))

        return left_anchor, right_anchor

    # ---------------------------------------------------------------------
    # Anchor creation
    # ---------------------------------------------------------------------

    def _floor_anchor_height(self, height: int) -> int:
        if height <= 0:
            return 1
        return max(1, (height // self.anchor_step) * self.anchor_step)

    async def _ensure_anchor(self, anchor_height: int) -> bool:
        """
        Ensures a single anchor exists for anchor_height.
        """
        if anchor_height <= 0:
            return False

        existing = await self._get_anchor_ts(anchor_height)
        if existing is not None:
            return True

        bucket = anchor_height // self.lock_bucket_size

        async with self._anchor_lock(str(bucket)) as acquired:
            if not acquired:
                # Another worker is likely creating anchors in this area.
                await asyncio.sleep(0.2)
                return (await self._get_anchor_ts(anchor_height)) is not None

            # Re-check after lock acquisition
            existing = await self._get_anchor_ts(anchor_height)
            if existing is not None:
                return True

            ts = await self.get_timestamp_by_block_height_precise(anchor_height)
            if ts < 0:
                return False

            await self._save_anchor(anchor_height, ts)
            return True

    async def _ensure_anchors_around(self, height: int, *, last_block: Optional[int] = None):
        """
        Ensures there are anchors suitable for interpolation around `height`.
        Typically creates floor and floor+step anchors.
        """
        if height <= 1:
            await self._ensure_anchor(1)
            return

        if last_block is None:
            last_block = await self.get_last_thorchain_block()

        left_h = self._floor_anchor_height(height)
        right_h = left_h + self.anchor_step

        # Clamp right anchor to last_block to avoid guaranteed misses near tip
        if right_h > last_block:
            right_h = max(1, self._floor_anchor_height(last_block))

        await self._ensure_anchor(left_h)
        if right_h != left_h:
            await self._ensure_anchor(right_h)

    # ---------------------------------------------------------------------
    # Interpolation/extrapolation
    # ---------------------------------------------------------------------

    def _should_densify(self, left: Anchor, right: Anchor) -> bool:
        span_blocks = right.height - left.height
        if span_blocks <= 0:
            return False

        # Too wide span => add more anchors
        if span_blocks > self.max_anchor_span_blocks:
            return True

        # If timestamps are inconsistent with expected block time, add more anchors
        expected_sec = span_blocks * THOR_BLOCK_TIME
        actual_sec = abs(right.ts - left.ts)

        # Avoid division by zero if constants are misconfigured
        if expected_sec <= 1:
            return False

        drift_ratio = abs(actual_sec - expected_sec) / expected_sec
        return drift_ratio > self.max_time_drift_ratio

    async def _densify_near(self, height: int, *, last_block: Optional[int] = None) -> None:
        # Prefer creating an anchor at the canonical grid
        h = self._floor_anchor_height(height)

        # If we already have it, do nothing
        if await self._get_anchor_ts(h) is not None:
            return

        # Create it (slow, locked)
        await self._ensure_anchor(h)

        # Optionally also ensure the next grid anchor for better right bound
        if last_block is None:
            last_block = await self.get_last_thorchain_block()

        h2 = h + self.anchor_step
        if h2 <= last_block and await self._get_anchor_ts(h2) is None:
            await self._ensure_anchor(h2)

    def _interpolate_ts(self, h: int, a: Anchor, b: Anchor) -> float:
        if a.height == b.height:
            return a.ts
        ratio = (h - a.height) / (b.height - a.height)
        return a.ts + ratio * (b.ts - a.ts)

    async def get_datetime_by_block_height(self, height: int, *, last_block: Optional[int] = None) -> datetime:
        """
        Fast approximate conversion: block height -> datetime.

        - Uses interpolation between anchors when possible
        - Creates anchors lazily (slow) if missing
        - Densifies anchors when the surrounding anchors are too far apart
        - Falls back to direct block timestamp query if still missing
        """
        if height <= 1:
            raise ValueError("Block height must be >= 1")

        left, right = await self._get_neighbor_anchors(height)

        if left is None or right is None:
            await self._ensure_anchors_around(height, last_block=last_block)
            left, right = await self._get_neighbor_anchors(height)

        if left and right:
            if self._should_densify(left, right):
                await self._densify_near(height, last_block=last_block)
                left, right = await self._get_neighbor_anchors(height)

            if left and right:
                ts = self._interpolate_ts(height, left, right)
                return self._ts_to_datetime(ts)

        if left:
            ts = left.ts + (height - left.height) * THOR_BLOCK_TIME
            return self._ts_to_datetime(ts)

        if right:
            ts = right.ts - (right.height - height) * THOR_BLOCK_TIME
            return self._ts_to_datetime(ts)

        ts = await self.get_timestamp_by_block_height_precise(height)
        return self._ts_to_datetime(ts if ts >= 0 else 0.0)
