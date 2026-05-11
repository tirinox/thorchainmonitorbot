from collections import defaultdict
from datetime import datetime
from typing import Optional, cast

from redis.asyncio import Redis
from jobs.scanner.event_db import EventDbTxDeduplicator
from jobs.scanner.block_result import BlockResult
from jobs.scanner.swap_props import group_rapid_swap_executions
from lib.accumulator import DailyAccumulator
from lib.active_users import DailyActiveUserCounter
from lib.constants import thor_to_float
from lib.date_utils import DAY, now_ts
from lib.delegates import INotified
from lib.depcont import DepContainer
from lib.logs import WithLogger
from models.events import EventSwap, parse_swap_and_out_event


class RapidSwapRecorder(INotified, WithLogger):
    """Persist rapid-swap adoption and efficiency statistics per day."""

    ACCUM_NAME = 'RapidSwaps'
    DEDUP_COMPONENT = 'rapid_swap_batch'
    RAPID_TX_COUNTER_NAME = 'RapidSwapTxs'
    TOTAL_SWAP_COUNTER_NAME = 'AllSwapTxs'
    RAPID_USER_COUNTER_NAME = 'RapidSwapUsers'

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.last_seen_block_no = 0
        self.last_rapid_candidates: dict[str, list[EventSwap]] = {}

        db = getattr(deps, 'db', None)
        lazy_redis = cast(Redis, cast(object, None))

        self.accumulator = DailyAccumulator(self.ACCUM_NAME, db) if db else None
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
    def _empty_snapshot() -> dict:
        return {
            'rapid_swap_count': 0.0,
            'total_swap_count': 0.0,
            'unique_users': 0.0,
            'rapid_swap_volume_usd': 0.0,
            'rapid_swap_blocks_saved': 0.0,
            'rapid_swap_event_count': 0.0,
        }

    @classmethod
    def _normalize_snapshot(cls, ts: float, raw: Optional[dict]) -> dict:
        snap = cls._empty_snapshot()
        if raw:
            for key in snap:
                if key in raw:
                    snap[key] = float(raw[key])

        rapid_swap_count = snap['rapid_swap_count']
        total_swap_count = snap['total_swap_count']
        snap['rapid_swap_share'] = rapid_swap_count / total_swap_count if total_swap_count else 0.0

        return {
            'date': cls._date_str(ts),
            'timestamp': int(ts),
            **snap,
        }

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

    async def _update_counter_snapshot(self, counter: DailyActiveUserCounter, ts: int, field_name: str, values: set[str]):
        if not (self.accumulator and counter and values):
            return

        await counter.hit(users=values, now=float(ts))
        dau = await counter.get_dau(float(ts))
        await self.accumulator.set(ts, **{field_name: dau})

    async def _update_total_swap_snapshot(self, ts: int, tx_ids: set[str]):
        await self._update_counter_snapshot(self._total_swap_counter, ts, 'total_swap_count', tx_ids)

    async def _update_rapid_uniques(self, ts: int, rapid_candidates: dict[str, list[EventSwap]]):
        rapid_tx_ids = set(rapid_candidates.keys())
        rapid_users = {
            swap_event.from_address
            for swap_events in rapid_candidates.values()
            for swap_event in swap_events
            if swap_event.from_address
        }

        await self._update_counter_snapshot(self._rapid_tx_counter, ts, 'rapid_swap_count', rapid_tx_ids)
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
            representative_events = [group[0] for group in execution_groups.values()]
            volume_usd = sum(self._price_swap_usd(swap_event, price_holder) for swap_event in representative_events)
            logical_swap_count = len(execution_groups)
            blocks_saved = max(0, logical_swap_count - 1)

            await self.accumulator.add(
                ts,
                rapid_swap_volume_usd=volume_usd,
                rapid_swap_blocks_saved=blocks_saved,
                rapid_swap_event_count=logical_swap_count,
            )

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

        end_ts = float(end_ts or now_ts())
        items = []
        for offset in range(days - 1, -1, -1):
            ts = end_ts - offset * DAY
            raw = await self.accumulator.get(ts)
            items.append(self._normalize_snapshot(ts, raw))
        return items

    async def _get_unique_counter_value(
        self,
        counter: Optional[DailyActiveUserCounter],
        days: int = 14,
        end_ts: Optional[float] = None,
    ) -> int:
        if not counter:
            return 0

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

        rapid_swap_count = totals['rapid_swap_count']
        total_swap_count = totals['total_swap_count']
        rapid_swap_share = rapid_swap_count / total_swap_count if total_swap_count else 0.0

        return {
            'days': days,
            'start_date': daily[0]['date'] if daily else '',
            'end_date': daily[-1]['date'] if daily else '',
            **totals,
            'rapid_swap_share': rapid_swap_share,
            'daily': daily,
        }

    async def on_data(self, sender, block: BlockResult):
        swap_events = list(self.iter_swap_events(block))
        grouped_by_tx_id = self._group_swap_events_by_tx_id(swap_events)

        self.last_seen_block_no = int(block.block_no or 0)
        self.last_rapid_candidates = {
            tx_id: swap_events
            for tx_id, swap_events in grouped_by_tx_id.items()
            if len(swap_events) > 1
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
