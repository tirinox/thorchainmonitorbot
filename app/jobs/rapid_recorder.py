import asyncio
import json
from collections import defaultdict
from datetime import UTC, datetime
from typing import Optional, cast

from redis.asyncio import Redis
from jobs.scanner.event_db import EventDatabase, EventDbTxDeduplicator
from jobs.scanner.block_result import BlockResult
from jobs.scanner.swap_props import group_rapid_swap_executions
from lib.accumulator import DailyAccumulator
from lib.active_users import DailyActiveUserCounter
from lib.constants import THOR_BLOCK_TIME, thor_to_float
from lib.date_utils import DAY, now_ts
from lib.delegates import INotified
from lib.depcont import DepContainer
from lib.logs import WithLogger
from models.asset import Asset
from models.events import EventSwap, parse_swap_and_out_event
from models.rapid_swap import (
    RapidSwapDailyPoint,
    RapidSwapDelta,
    RapidSwapDeltas,
    RapidSwapLargestSwap,
    RapidSwapPeriodStats,
    RapidSwapTopPairStats,
    RapidSwapTotals,
)


class RapidSwapRecorder(INotified, WithLogger):
    """Persist rapid-swap adoption and efficiency statistics per day."""

    ACCUM_NAME = 'RapidSwaps'
    DEDUP_COMPONENT = 'rapid_swap_batch'
    RAPID_TX_COUNTER_NAME = 'RapidSwapTxs'
    TOTAL_SWAP_COUNTER_NAME = 'AllSwapTxs'
    RAPID_USER_COUNTER_NAME = 'RapidSwapUsers'
    META_PREFIX = 'RapidSwap:Meta'

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.last_seen_block_no = 0
        self.last_rapid_candidates: dict[str, list[EventSwap]] = {}

        db = getattr(deps, 'db', None)
        lazy_redis = cast(Redis, cast(object, None))

        self.accumulator = DailyAccumulator(self.ACCUM_NAME, db) if db else None
        self._event_db = EventDatabase(db) if db else None
        self._rapid_batch_dedup = EventDbTxDeduplicator(db, self.DEDUP_COMPONENT) if db else None
        self._rapid_tx_counter = DailyActiveUserCounter(lazy_redis, self.RAPID_TX_COUNTER_NAME) if db else None
        self._total_swap_counter = DailyActiveUserCounter(lazy_redis, self.TOTAL_SWAP_COUNTER_NAME) if db else None
        self._rapid_user_counter = DailyActiveUserCounter(lazy_redis, self.RAPID_USER_COUNTER_NAME) if db else None

    @staticmethod
    def iter_swap_events(block: BlockResult):
        for raw_event in block.end_block_events:
            parsed_event = parse_swap_and_out_event(raw_event)
            if isinstance(parsed_event, EventSwap):
                yield parsed_event

    @staticmethod
    def _group_swap_events_by_tx_id(swap_events: list[EventSwap]) -> dict[str, list[EventSwap]]:
        grouped_by_tx_id: dict[str, list[EventSwap]] = defaultdict(list)
        for swap_event in swap_events:
            if swap_event.tx_id:
                grouped_by_tx_id[swap_event.tx_id].append(swap_event)
        return grouped_by_tx_id

    def collect_rapid_swap_candidates(self, block: BlockResult) -> dict[str, list[EventSwap]]:
        grouped_by_tx_id = self._group_swap_events_by_tx_id(list(self.iter_swap_events(block)))
        return {
            tx_id: swap_events
            for tx_id, swap_events in grouped_by_tx_id.items()
            if len(group_rapid_swap_executions(swap_events)) > 1
        }

    @staticmethod
    def _dedup_key(block_no: int, tx_id: str) -> str:
        return f'{int(block_no or 0)}:{tx_id}'

    @staticmethod
    def _date_str(ts: float) -> str:
        return datetime.fromtimestamp(ts).strftime('%Y-%m-%d')

    @staticmethod
    def _utc_date_time_str(ts: float) -> str:
        return datetime.fromtimestamp(ts, UTC).strftime('%Y-%m-%d %H:%M UTC')

    @classmethod
    def _meta_key(cls, ts: float) -> str:
        # Keep per-batch metadata in daily Redis hashes for later period rollups.
        return f'{cls.META_PREFIX}:{cls._date_str(ts)}'

    @classmethod
    def _meta_keys_for_days(cls, days: int, end_ts: float) -> list[str]:
        return [cls._meta_key(ts) for ts in cls._build_daily_timestamps(days, end_ts)]

    @staticmethod
    def _parse_amount_asset(raw: str) -> str:
        raw = str(raw or '').strip()
        if not raw:
            return ''

        parts = raw.split(maxsplit=1)
        return parts[-1].strip() if parts else ''

    @classmethod
    def _normalize_asset_name(cls, asset: str) -> str:
        # Collapse synth/trade/secured forms into canonical L1 pool asset.
        asset = cls._parse_amount_asset(asset)
        if not asset:
            return ''

        try:
            return Asset.from_string(asset).l1_asset.native_pool_name
        except Exception:
            return asset

    @classmethod
    def _pretty_asset_name(cls, asset: str) -> str:
        # Use short human label when asset can be safely abbreviated.
        normalized = cls._normalize_asset_name(asset)
        if not normalized:
            return ''

        try:
            return Asset.from_string(normalized).l1_asset.pretty_str_no_emoji
        except Exception:
            return normalized

    @classmethod
    def _pair_key_and_label(cls, asset_a: str, asset_b: str) -> tuple[str, str]:
        # Sort normalized assets so forward/reverse routes land in one bucket.
        left = cls._normalize_asset_name(asset_a)
        right = cls._normalize_asset_name(asset_b)

        if not left and not right:
            return '', ''
        if not left:
            left = right
        if not right:
            right = left

        left, right = sorted([left, right])
        return f'{left}->{right}', f'{cls._pretty_asset_name(left)} → {cls._pretty_asset_name(right)}'

    @classmethod
    def _derive_pair_key_and_label(cls, representative_events: list[EventSwap]) -> tuple[str, str]:
        # Path = first input asset -> final emitted asset for rapid batch.
        if not representative_events:
            return '', ''

        first_event = representative_events[0]
        last_event = representative_events[-1]
        input_asset = first_event.asset or cls._parse_amount_asset(first_event.coin)
        output_asset = cls._parse_amount_asset(last_event.emit_asset) or last_event.asset or input_asset
        return cls._pair_key_and_label(input_asset, output_asset)

    @classmethod
    def _build_batch_meta(
        cls,
        ts: int,
        tx_id: str,
        representative_events: list[EventSwap],
        volume_usd: float,
        logical_swap_count: int,
        blocks_saved: int,
    ) -> dict:
        # Store one record per rapid batch; period views aggregate these later.
        pair_key, pair_label = cls._derive_pair_key_and_label(representative_events)
        blocks_used = max(0, logical_swap_count - blocks_saved)
        saved_time_sec = float(blocks_saved * THOR_BLOCK_TIME)
        faster_pct = float(blocks_saved / logical_swap_count * 100.0) if logical_swap_count else 0.0
        trader = next((ev.from_address for ev in representative_events if ev.from_address), '')

        return {
            'tx_id': tx_id,
            'timestamp': int(ts),
            'pair': pair_key,
            'pair_label': pair_label,
            'trader': trader,
            'usd_volume': round(float(volume_usd or 0.0), 4),
            'subswaps': int(logical_swap_count or 0),
            'blocks_used': int(blocks_used or 0),
            'blocks_saved': int(blocks_saved or 0),
            'saved_time_sec': saved_time_sec,
            'faster_pct': round(faster_pct, 4),
        }

    async def _store_batch_meta(self, ts: int, tx_id: str, payload: dict):
        # Field name = tx id so duplicate writes replace same batch deterministically.
        redis = await self.deps.db.get_redis()
        await redis.hset(self._meta_key(ts), tx_id, json.dumps(payload))

    async def _load_batch_meta_records(self, days: int, end_ts: float) -> list[dict]:
        # Read only last N daily buckets; no historical backfill scan.
        db = getattr(self.deps, 'db', None)
        if not db or days <= 0:
            return []

        redis = await db.get_redis()
        records = []
        for key in self._meta_keys_for_days(days, end_ts):
            raw_items = await redis.hgetall(key)
            for raw in raw_items.values():
                try:
                    records.append(json.loads(raw))
                except (TypeError, json.JSONDecodeError):
                    continue
        return records

    @staticmethod
    def _aggregate_top_pairs(records: list[dict]) -> list[RapidSwapTopPairStats]:
        # Group by normalized pair and aggregate usage/volume/time-saved metrics.
        grouped = defaultdict(lambda: {
            'pair_label': '',
            'rapid_swap_count': 0,
            'rapid_swap_volume_usd': 0.0,
            'subswaps_sum': 0.0,
            'faster_pct_sum': 0.0,
            'estimated_time_saved_sec': 0.0,
        })

        for record in records:
            pair_key = str(record.get('pair', '') or '')
            if not pair_key:
                continue

            bucket = grouped[pair_key]
            bucket['pair_label'] = str(record.get('pair_label', '') or pair_key)
            bucket['rapid_swap_count'] += 1
            bucket['rapid_swap_volume_usd'] += float(record.get('usd_volume', 0.0) or 0.0)
            bucket['subswaps_sum'] += float(record.get('subswaps', 0.0) or 0.0)
            bucket['faster_pct_sum'] += float(record.get('faster_pct', 0.0) or 0.0)
            bucket['estimated_time_saved_sec'] += float(record.get('saved_time_sec', 0.0) or 0.0)

        top_pairs = [
            RapidSwapTopPairStats(
                pair_label=data['pair_label'],
                rapid_swap_count=int(data['rapid_swap_count']),
                rapid_swap_volume_usd=round(float(data['rapid_swap_volume_usd']), 2),
                avg_subswaps=round(data['subswaps_sum'] / data['rapid_swap_count'], 4),
                avg_faster_pct=round(data['faster_pct_sum'] / data['rapid_swap_count'], 2),
                estimated_time_saved_sec=float(data['estimated_time_saved_sec']),
            )
            for data in grouped.values()
            if data['rapid_swap_count'] > 0
        ]

        top_pairs.sort(
            key=lambda item: (-item.rapid_swap_volume_usd, -item.rapid_swap_count, -item.estimated_time_saved_sec, item.pair_label)
        )
        return top_pairs

    @classmethod
    def _build_largest_swap(cls, records: list[dict]) -> RapidSwapLargestSwap:
        # Best swap = largest USD volume; tie-break by saved time, subswaps, tx id.
        if not records:
            return RapidSwapLargestSwap()

        record = sorted(
            records,
            key=lambda item: (
                -float(item.get('usd_volume', 0.0) or 0.0),
                -float(item.get('saved_time_sec', 0.0) or 0.0),
                -int(item.get('subswaps', 0) or 0),
                str(item.get('tx_id', '') or ''),
            ),
        )[0]

        blocks_used = int(record.get('blocks_used', 0) or 0)
        subswaps = int(record.get('subswaps', 0) or 0)
        efficiency_ratio = round(subswaps / blocks_used, 4) if blocks_used > 0 else 0.0

        return RapidSwapLargestSwap(
            when=cls._utc_date_time_str(float(record.get('timestamp', 0) or 0)),
            tx_id=str(record.get('tx_id', '') or ''),
            pair_label=str(record.get('pair_label', '') or ''),
            trader=str(record.get('trader', '') or ''),
            usd_volume=round(float(record.get('usd_volume', 0.0) or 0.0), 2),
            subswaps=subswaps,
            blocks_used=blocks_used,
            blocks_saved=int(record.get('blocks_saved', 0) or 0),
            saved_time_sec=float(record.get('saved_time_sec', 0.0) or 0.0),
            faster_pct=round(float(record.get('faster_pct', 0.0) or 0.0), 2),
            efficiency_ratio=efficiency_ratio,
        )

    @staticmethod
    def _empty_snapshot() -> dict:
        return {
            'rapid_swap_count': 0.0,
            'total_swap_count': 0.0,
            'unique_users': 0.0,
            'rapid_swap_volume_usd': 0.0,
            'rapid_swap_blocks_saved': 0.0,
            'rapid_swap_event_count': 0.0,
        }

    @staticmethod
    def _with_derived_metrics(snap: dict) -> dict:
        rapid_swap_count = float(snap.get('rapid_swap_count', 0.0))
        total_swap_count = float(snap.get('total_swap_count', 0.0))
        blocks_saved = float(snap.get('rapid_swap_blocks_saved', 0.0))

        return {
            **snap,
            'rapid_swap_share': rapid_swap_count / total_swap_count if total_swap_count else 0.0,
            'estimated_time_saved_sec': blocks_saved * THOR_BLOCK_TIME,
        }

    @classmethod
    def _normalize_snapshot(cls, ts: float, raw: Optional[dict]) -> dict:
        snap = cls._empty_snapshot()
        if raw:
            for key in snap:
                if key in raw:
                    snap[key] = float(raw[key])
        snap = cls._with_derived_metrics(snap)

        return {
            'date': cls._date_str(ts),
            'timestamp': int(ts),
            **snap,
        }

    @staticmethod
    def _build_daily_timestamps(days: int, end_ts: float) -> list[float]:
        return [end_ts - offset * DAY for offset in range(days - 1, -1, -1)]

    async def _get_cumulative_counter_values(
        self,
        counter: Optional[DailyActiveUserCounter],
        timestamps: list[float],
    ) -> list[int]:
        if not counter or not timestamps:
            return [0] * len(timestamps)

        if getattr(counter, 'r', None) is None:
            await self._ensure_counters_ready()

        counts = []
        postfixes = []
        for ts in timestamps:
            postfixes.append(counter.key_postfix(ts))
            counts.append(int(await counter.get_count(postfixes)))
        return counts

    async def _get_price_holder(self):
        pool_cache = getattr(self.deps, 'pool_cache', None)
        if not pool_cache:
            return None
        try:
            return await pool_cache.get()
        except Exception as e:
            self.logger.warning(f'Failed to load pool cache for RapidSwapRecorder: {e!r}')
            return None

    async def _ensure_counters_ready(self):
        db = getattr(self.deps, 'db', None)
        if not db:
            return

        redis = getattr(db, 'redis', None)
        if redis is None:
            redis = await db.get_redis()

        for counter in (self._rapid_tx_counter, self._total_swap_counter, self._rapid_user_counter):
            if counter:
                counter.r = redis

    def _price_swap_usd(self, swap_event: EventSwap, price_holder) -> float:
        if not price_holder or not swap_event.asset or not swap_event.amount:
            return 0.0

        try:
            amount_float = thor_to_float(swap_event.amount)
            return float(price_holder.convert_to_usd(amount_float, swap_event.asset) or 0.0)
        except Exception as e:
            self.logger.warning(f'Failed to price rapid swap event {swap_event.tx_id}: {e!r}')
            return 0.0

    async def _price_full_swap_usd(
        self,
        tx_id: str,
        representative_events: list[EventSwap],
        price_holder,
    ) -> float:
        # Prefer full inbound tx size; fallback to sum of logical sub-swap pieces.
        if not price_holder:
            return 0.0

        if tx_id and self._event_db:
            try:
                if props := await self._event_db.read_tx_status(tx_id):
                    in_coin = props.in_coin
                    if in_coin.asset and in_coin.amount:
                        amount_float = thor_to_float(in_coin.amount)
                        usd_volume = float(price_holder.convert_to_usd(amount_float, in_coin.asset) or 0.0)
                        if usd_volume > 0.0:
                            return usd_volume
            except Exception as e:
                self.logger.warning(f'Failed to price full rapid swap tx {tx_id}: {e!r}')

        return sum(self._price_swap_usd(swap_event, price_holder) for swap_event in representative_events)

    async def _update_counter_snapshot(self, counter: DailyActiveUserCounter, ts: int, field_name: str, values: set[str]):
        if not (self.accumulator and counter and values):
            return

        await counter.hit(users=values, now=float(ts))
        dau = await counter.get_dau(float(ts))
        await self.accumulator.set(ts, **{field_name: dau})

    async def _update_total_swap_snapshot(self, ts: int, tx_ids: set[str]):
        if self._total_swap_counter:
            await self._update_counter_snapshot(self._total_swap_counter, ts, 'total_swap_count', tx_ids)

    async def _update_rapid_uniques(self, ts: int, rapid_candidates: dict[str, list[EventSwap]]):
        rapid_tx_ids = set(rapid_candidates.keys())
        rapid_users = {
            swap_event.from_address
            for swap_events in rapid_candidates.values()
            for swap_event in swap_events
            if swap_event.from_address
        }

        if self._rapid_tx_counter:
            await self._update_counter_snapshot(self._rapid_tx_counter, ts, 'rapid_swap_count', rapid_tx_ids)
        if self._rapid_user_counter:
            await self._update_counter_snapshot(self._rapid_user_counter, ts, 'unique_users', rapid_users)

    async def _persist_new_rapid_batches(
        self,
        block: BlockResult,
        ts: int,
        rapid_candidates: dict[str, list[EventSwap]],
        price_holder,
    ):
        if not (self.accumulator and rapid_candidates):
            return

        batch_map = {
            self._dedup_key(block.block_no, tx_id): (tx_id, swap_events)
            for tx_id, swap_events in rapid_candidates.items()
        }

        if self._rapid_batch_dedup:
            new_batch_keys = await self._rapid_batch_dedup.only_new_hashes(list(batch_map.keys()))
        else:
            new_batch_keys = list(batch_map.keys())

        for batch_key in new_batch_keys:
            tx_id, swap_events = batch_map[batch_key]
            execution_groups = group_rapid_swap_executions(swap_events)
            # One representative event per logical execution keeps volume/path math stable.
            representative_events = [group[0] for group in execution_groups.values()]
            volume_usd = await self._price_full_swap_usd(tx_id, representative_events, price_holder)
            logical_swap_count = len(execution_groups)
            blocks_saved = max(0, logical_swap_count - 1)
            batch_meta = self._build_batch_meta(
                ts,
                tx_id,
                representative_events,
                volume_usd,
                logical_swap_count,
                blocks_saved,
            )

            await self.accumulator.add(
                ts,
                rapid_swap_volume_usd=volume_usd,
                rapid_swap_blocks_saved=blocks_saved,
                rapid_swap_event_count=logical_swap_count,
            )
            await self._store_batch_meta(ts, tx_id, batch_meta)

            if self._rapid_batch_dedup:
                await self._rapid_batch_dedup.mark_as_seen(batch_key)

            self.logger.debug(
                f'Recorded rapid swap batch tx={tx_id} block={block.block_no} '
                f'events={len(swap_events)} logical_swaps={logical_swap_count} '
                f'blocks_saved={blocks_saved} volume_usd={volume_usd:.2f}'
            )

    async def get_daily_data(self, days: int = 14, end_ts: Optional[float] = None) -> list[dict]:
        if days <= 0:
            raise ValueError('days must be > 0')

        if not self.accumulator:
            return []

        await self.deps.db.get_redis()

        end_ts = float(end_ts or now_ts())
        timestamps = self._build_daily_timestamps(days, end_ts)
        items = []
        for ts in timestamps:
            raw = await self.accumulator.get(ts)
            items.append(self._normalize_snapshot(ts, raw))

        cumulative_unique_users = await self._get_cumulative_counter_values(self._rapid_user_counter, timestamps)

        cumulative_tx_count = 0.0
        cumulative_volume_usd = 0.0
        cumulative_saved_sec = 0.0
        for item, cumulative_users in zip(items, cumulative_unique_users):
            cumulative_tx_count += float(item.get('rapid_swap_count', 0.0))
            cumulative_volume_usd += float(item.get('rapid_swap_volume_usd', 0.0))
            cumulative_saved_sec += float(item.get('estimated_time_saved_sec', 0.0))

            item['cumulative_rapid_swap_count'] = cumulative_tx_count
            item['cumulative_rapid_swap_volume_usd'] = cumulative_volume_usd
            item['cumulative_estimated_time_saved_sec'] = cumulative_saved_sec
            item['cumulative_unique_users'] = float(cumulative_users)
        return items

    async def _get_unique_counter_value(
        self,
        counter: Optional[DailyActiveUserCounter],
        days: int = 14,
        end_ts: Optional[float] = None,
    ) -> int:
        if not counter:
            return 0

        if getattr(counter, 'r', None) is None:
            await self._ensure_counters_ready()

        end_ts = float(end_ts or now_ts())
        postfixes = [
            counter.key_postfix(end_ts - offset * DAY)
            for offset in range(days - 1, -1, -1)
        ]
        return int(await counter.get_count(postfixes))

    async def get_summary(self, days: int = 14, end_ts: Optional[float] = None) -> dict:
        daily = await self.get_daily_data(days=days, end_ts=end_ts)

        totals = self._empty_snapshot()
        additive_keys = {'rapid_swap_volume_usd', 'rapid_swap_blocks_saved', 'rapid_swap_event_count'}
        for day in daily:
            for key in additive_keys:
                totals[key] += float(day.get(key, 0.0))

        end_ts = float(end_ts or now_ts())
        totals['rapid_swap_count'] = float(
            await self._get_unique_counter_value(self._rapid_tx_counter, days=days, end_ts=end_ts)
        )
        totals['total_swap_count'] = float(
            await self._get_unique_counter_value(self._total_swap_counter, days=days, end_ts=end_ts)
        )
        totals['unique_users'] = float(
            await self._get_unique_counter_value(self._rapid_user_counter, days=days, end_ts=end_ts)
        )

        totals = self._with_derived_metrics(totals)

        return {
            'days': days,
            'start_date': daily[0]['date'] if daily else '',
            'end_date': daily[-1]['date'] if daily else '',
            **totals,
            'daily': daily,
        }

    @staticmethod
    def _safe_pct_change(current: float, previous: float) -> float:
        return round((current - previous) / previous * 100.0, 2) if previous else 0.0

    @staticmethod
    def _build_totals(summary: dict) -> RapidSwapTotals:
        rapid_swap_count = int(summary.get('rapid_swap_count', 0.0) or 0)
        total_swap_count = int(summary.get('total_swap_count', 0.0) or 0)
        unique_users = int(summary.get('unique_users', 0.0) or 0)
        rapid_swap_volume_usd = round(float(summary.get('rapid_swap_volume_usd', 0.0) or 0.0), 2)
        rapid_swap_blocks_saved = int(summary.get('rapid_swap_blocks_saved', 0.0) or 0)
        rapid_swap_event_count = int(summary.get('rapid_swap_event_count', 0.0) or 0)
        rapid_swap_share = float(summary.get('rapid_swap_share', 0.0) or 0.0)
        estimated_time_saved_sec = float(summary.get('estimated_time_saved_sec', 0.0) or 0.0)

        blocks_used = max(0, rapid_swap_event_count - rapid_swap_blocks_saved)
        avg_subswaps_per_tx = rapid_swap_event_count / rapid_swap_count if rapid_swap_count else 0.0
        avg_faster_pct = rapid_swap_blocks_saved / rapid_swap_event_count * 100.0 if rapid_swap_event_count else 0.0
        efficiency_ratio = rapid_swap_event_count / blocks_used if blocks_used > 0 else 0.0

        return RapidSwapTotals(
            rapid_swap_count=rapid_swap_count,
            total_swap_count=total_swap_count,
            unique_users=unique_users,
            rapid_swap_volume_usd=rapid_swap_volume_usd,
            rapid_swap_blocks_saved=rapid_swap_blocks_saved,
            rapid_swap_event_count=rapid_swap_event_count,
            rapid_swap_share=rapid_swap_share,
            estimated_time_saved_sec=estimated_time_saved_sec,
            avg_subswaps_per_tx=round(avg_subswaps_per_tx, 4),
            avg_faster_pct=round(avg_faster_pct, 2),
            efficiency_ratio=round(efficiency_ratio, 4),
        )

    async def get_infographic_data(
        self,
        days: int = 7,
        end_ts: Optional[float] = None,
    ) -> RapidSwapPeriodStats:
        if days <= 0:
            raise ValueError('days must be > 0')

        end_ts = float(end_ts or now_ts())
        prev_end_ts = end_ts - days * DAY

        # Load summaries and raw batch records together; infographic needs both layers.
        current_summary, previous_summary, current_records = await asyncio.gather(
            self.get_summary(days=days, end_ts=end_ts),
            self.get_summary(days=days, end_ts=prev_end_ts),
            self._load_batch_meta_records(days=days, end_ts=end_ts),
        )

        current_total = self._build_totals(current_summary)
        previous_total = self._build_totals(previous_summary)
        top_pairs = self._aggregate_top_pairs(current_records)
        largest_swap = self._build_largest_swap(current_records)

        daily_points = [
            RapidSwapDailyPoint(
                date=day.get('date', ''),
                rapid_swap_count=int(day.get('rapid_swap_count', 0.0) or 0),
                total_swap_count=int(day.get('total_swap_count', 0.0) or 0),
                unique_users=int(day.get('unique_users', 0.0) or 0),
                rapid_swap_volume_usd=round(float(day.get('rapid_swap_volume_usd', 0.0) or 0.0), 2),
                rapid_swap_blocks_saved=int(day.get('rapid_swap_blocks_saved', 0.0) or 0),
                rapid_swap_event_count=int(day.get('rapid_swap_event_count', 0.0) or 0),
                rapid_swap_share=float(day.get('rapid_swap_share', 0.0) or 0.0),
                estimated_time_saved_sec=float(day.get('estimated_time_saved_sec', 0.0) or 0.0),
                cumulative_rapid_swap_count=int(day.get('cumulative_rapid_swap_count', 0.0) or 0),
                cumulative_rapid_swap_volume_usd=round(float(day.get('cumulative_rapid_swap_volume_usd', 0.0) or 0.0), 2),
                cumulative_estimated_time_saved_sec=float(day.get('cumulative_estimated_time_saved_sec', 0.0) or 0.0),
                cumulative_unique_users=int(day.get('cumulative_unique_users', 0.0) or 0),
                avg_subswaps_per_tx=round(float(day.get('rapid_swap_event_count', 0.0) or 0.0) / float(day.get('rapid_swap_count', 0.0) or 1.0), 4)
                if day.get('rapid_swap_count', 0.0) else 0.0,
                avg_faster_pct=round(
                    float(day.get('rapid_swap_blocks_saved', 0.0) or 0.0)
                    / float(day.get('rapid_swap_event_count', 0.0) or 1.0) * 100.0,
                    2,
                ) if day.get('rapid_swap_event_count', 0.0) else 0.0,
            )
            for day in current_summary.get('daily', [])
        ]

        return RapidSwapPeriodStats(
            period_days=days,
            start_date=current_summary.get('start_date', ''),
            end_date=current_summary.get('end_date', ''),
            total=current_total,
            previous=previous_total,
            delta=RapidSwapDeltas(
                rapid_swap_count=RapidSwapDelta(
                    absolute=round(current_total.rapid_swap_count - previous_total.rapid_swap_count, 4),
                    pct=self._safe_pct_change(current_total.rapid_swap_count, previous_total.rapid_swap_count),
                ),
                rapid_swap_volume_usd=RapidSwapDelta(
                    absolute=round(current_total.rapid_swap_volume_usd - previous_total.rapid_swap_volume_usd, 4),
                    pct=self._safe_pct_change(current_total.rapid_swap_volume_usd, previous_total.rapid_swap_volume_usd),
                ),
                unique_users=RapidSwapDelta(
                    absolute=round(current_total.unique_users - previous_total.unique_users, 4),
                    pct=self._safe_pct_change(current_total.unique_users, previous_total.unique_users),
                ),
                estimated_time_saved_sec=RapidSwapDelta(
                    absolute=round(current_total.estimated_time_saved_sec - previous_total.estimated_time_saved_sec, 4),
                    pct=self._safe_pct_change(current_total.estimated_time_saved_sec, previous_total.estimated_time_saved_sec),
                ),
                rapid_swap_share_pp=RapidSwapDelta(
                    absolute=round((current_total.rapid_swap_share - previous_total.rapid_swap_share) * 100.0, 4),
                    pct=self._safe_pct_change(current_total.rapid_swap_share, previous_total.rapid_swap_share),
                ),
            ),
            daily=daily_points,
            top_pairs=top_pairs,
            largest_swap=largest_swap,
        )

    async def on_data(self, sender, block: BlockResult):
        swap_events = list(self.iter_swap_events(block))
        grouped_by_tx_id = self._group_swap_events_by_tx_id(swap_events)

        self.last_seen_block_no = int(block.block_no or 0)
        self.last_rapid_candidates = {
            tx_id: swap_events
            for tx_id, swap_events in grouped_by_tx_id.items()
            if len(group_rapid_swap_executions(swap_events)) > 1
        }

        ts = int(block.timestamp or now_ts())

        await self._ensure_counters_ready()

        await self._update_total_swap_snapshot(ts, set(grouped_by_tx_id.keys()))
        await self._update_rapid_uniques(ts, self.last_rapid_candidates)

        if self.last_rapid_candidates:
            price_holder = await self._get_price_holder()
            await self._persist_new_rapid_batches(block, ts, self.last_rapid_candidates, price_holder)

        if self.last_rapid_candidates:
            self.logger.info(
                f'RapidSwapRecorder found {len(self.last_rapid_candidates)} '
                f'rapid-swap candidate txs in block #{block.block_no}'
            )
