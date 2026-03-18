import asyncio
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from api.aionode.types import thor_to_float
from jobs.scanner.limit_detector import LimitSwapBlockUpdate, ClosedLimitSwap
from jobs.scanner.tx import NativeThorTx, ThorEvent, ThorTxMessage
from lib.accumulator import DailyAccumulator
from lib.active_users import DailyActiveUserCounter
from lib.date_utils import now_ts, DAY
from lib.delegates import INotified
from lib.depcont import DepContainer
from lib.logs import WithLogger
from lib.utils import async_once_every
from models.asset import Asset, is_rune
from models.events import EventSwap
from models.limit_swap import (
    LimitSwapDailyPoint, LimitSwapDelta, LimitSwapDeltas,
    LimitSwapPairStats, LimitSwapPeriodStats, LimitSwapTotals,
)
from models.memo import THORMemo, ActionType
from notify.dup_stop import TxDeduplicator


@dataclass
class OpenLimitSwapMeta:
    tx_hash: str
    block_no: int
    timestamp: int
    source_asset: str
    target_asset: str
    usd_amount: float
    trader: str = ''

    def to_json(self):
        return json.dumps({
            'tx_hash': self.tx_hash,
            'block_no': self.block_no,
            'timestamp': self.timestamp,
            'source_asset': self.source_asset,
            'target_asset': self.target_asset,
            'usd_amount': self.usd_amount,
            'trader': self.trader,
        })

    @classmethod
    def from_json(cls, raw: str):
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return None
        return cls(
            tx_hash=str(data.get('tx_hash', '')),
            block_no=int(data.get('block_no', 0)),
            timestamp=int(data.get('timestamp', 0)),
            source_asset=str(data.get('source_asset', '')),
            target_asset=str(data.get('target_asset', '')),
            usd_amount=float(data.get('usd_amount', 0.0)),
            trader=str(data.get('trader', '')),
        )


class LimitSwapStatsRecorder(WithLogger, INotified):
    ACCUM_NAME = 'LimitSwaps'
    OPEN_META_KEY = 'LimitSwap:open-meta:v1'
    OPEN_META_RETENTION_SEC = 90 * DAY
    OPEN_META_CLEAN_EVERY_N_UPDATES = 50

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.accumulator = DailyAccumulator(self.ACCUM_NAME, deps.db)
        self._opened_dedup = None
        self._partial_dedup = None
        self._closed_dedup = None
        self._trader_counter: DailyActiveUserCounter | None = None
        self._pair_trader_counters: dict[str, DailyActiveUserCounter] = {}

    @staticmethod
    def _slug(value: str) -> str:
        return re.sub(r'[^a-z0-9]+', '_', value.lower()).strip('_')

    @staticmethod
    def _canonical_pair(asset_a: str, asset_b: str) -> tuple[str, str]:
        """Return the two asset strings sorted alphabetically so pair order is canonical."""
        a, b = sorted([asset_a, asset_b])
        return a, b

    @classmethod
    def _pair_canonical_name(cls, asset_a: str, asset_b: str) -> str:
        a, b = cls._canonical_pair(asset_a, asset_b)
        return f'{a}->{b}'

    @classmethod
    def _pair_count_key(cls, source_asset: str, target_asset: str) -> str:
        return f'pair:{cls._pair_canonical_name(source_asset, target_asset)}:opened_count'

    @classmethod
    def _pair_usd_key(cls, source_asset: str, target_asset: str) -> str:
        return f'pair:{cls._pair_canonical_name(source_asset, target_asset)}:opened_usd'

    @classmethod
    def _pair_traders_key(cls, source_asset: str, target_asset: str) -> str:
        return f'pair:{cls._pair_canonical_name(source_asset, target_asset)}:unique_traders'

    @classmethod
    def _close_reason_key(cls, reason: str) -> str:
        slug = cls._slug(reason) or 'unknown'
        return f'closed_reason:{slug}'

    @staticmethod
    def _date_str(ts: int) -> str:
        return datetime.fromtimestamp(ts).strftime('%Y-%m-%d')

    @staticmethod
    def _empty_metrics() -> dict:
        return {
            'opened_count': 0.0,
            'opened_usd': 0.0,
            'unique_traders': 0.0,
            'partial_count': 0.0,
            'partial_usd': 0.0,
            'closed_count': 0.0,
            'closed_duration_blocks_sum': 0.0,
            'closed_duration_samples': 0.0,
            'avg_duration_blocks': 0.0,
        }

    @classmethod
    def _normalize_daily_snapshot(cls, ts: int, raw: dict | None):
        raw = raw or {}
        metrics = cls._empty_metrics()
        pairs = defaultdict(lambda: {'opened_count': 0.0, 'opened_usd': 0.0, 'unique_traders': 0.0})
        close_reasons = {}

        for key, value in raw.items():
            value = float(value)
            if key in metrics:
                metrics[key] = value
                continue

            if key.startswith('pair:') and key.endswith(':opened_count'):
                pair_name = key[len('pair:'):-len(':opened_count')]
                pairs[pair_name]['opened_count'] = value
                continue

            if key.startswith('pair:') and key.endswith(':opened_usd'):
                pair_name = key[len('pair:'):-len(':opened_usd')]
                pairs[pair_name]['opened_usd'] = value
                continue

            if key.startswith('pair:') and key.endswith(':unique_traders'):
                pair_name = key[len('pair:'):-len(':unique_traders')]
                pairs[pair_name]['unique_traders'] = value
                continue

            if key.startswith('closed_reason:'):
                close_reasons[key[len('closed_reason:'):]] = value

        return {
            'date': cls._date_str(ts),
            'timestamp': int(ts),
            **metrics,
            'pairs': dict(pairs),
            'close_reasons': close_reasons,
        }

    async def get_daily_data(self, days: int = 14, end_ts: int | None = None):
        if days <= 0:
            raise ValueError('days must be > 0')

        end_ts = int(end_ts or now_ts())
        items = []
        for offset in range(days - 1, -1, -1):
            ts = end_ts - offset * DAY
            raw = await self.accumulator.get(ts)
            items.append(self._normalize_daily_snapshot(ts, raw))
        return items

    async def get_unique_traders(self, days: int = 14, end_ts: int | None = None) -> int:
        await self._ensure_runtime_resources()
        end_ts = int(end_ts or now_ts())
        postfixes = [
            self._trader_counter.key_postfix(end_ts - offset * DAY)
            for offset in range(days - 1, -1, -1)
        ]
        return int(await self._trader_counter.get_count(postfixes))

    async def get_pair_unique_traders(
        self,
        pair_canonical_name: str,
        days: int = 14,
        end_ts: int | None = None,
    ) -> int:
        """Return the true (HyperLogLog-based) unique trader count for a canonical pair over *days*."""
        await self._ensure_runtime_resources()
        end_ts = int(end_ts or now_ts())
        counter = self._get_pair_trader_counter(pair_canonical_name)
        postfixes = [
            counter.key_postfix(end_ts - offset * DAY)
            for offset in range(days - 1, -1, -1)
        ]
        return int(await counter.get_count(postfixes))

    async def get_summary(self, days: int = 14, end_ts: int | None = None):
        await self._ensure_runtime_resources()
        end_ts = int(end_ts or now_ts())
        daily = await self.get_daily_data(days=days, end_ts=end_ts)

        summary = self._empty_metrics()
        pair_summary = defaultdict(lambda: {'opened_count': 0.0, 'opened_usd': 0.0, 'unique_traders': 0.0})
        close_reason_summary = defaultdict(float)

        for day in daily:
            for key in summary.keys():
                if key == 'avg_duration_blocks':
                    continue
                summary[key] += float(day.get(key, 0.0))

            for pair_name, pair_data in day.get('pairs', {}).items():
                pair_summary[pair_name]['opened_count'] += float(pair_data.get('opened_count', 0.0))
                pair_summary[pair_name]['opened_usd'] += float(pair_data.get('opened_usd', 0.0))

            for reason, count in day.get('close_reasons', {}).items():
                close_reason_summary[reason] += float(count)

        duration_sum = summary['closed_duration_blocks_sum']
        duration_samples = summary['closed_duration_samples']
        summary['avg_duration_blocks'] = duration_sum / duration_samples if duration_samples else 0.0

        unique_trader_values = [float(day.get('unique_traders', 0.0)) for day in daily]
        total_unique_traders = await self.get_unique_traders(days=days, end_ts=end_ts)
        total_unique_trader_days = sum(unique_trader_values)
        summary['unique_traders'] = float(total_unique_traders)

        # Compute true multi-day unique traders per pair via HyperLogLog pfcount.
        all_pair_names = set()
        for day in daily:
            all_pair_names.update(day.get('pairs', {}).keys())
        for pair_name in all_pair_names:
            pair_summary[pair_name]['unique_traders'] = await self.get_pair_unique_traders(
                pair_name, days=days, end_ts=end_ts
            )

        return {
            'days': days,
            'start_date': daily[0]['date'] if daily else '',
            'end_date': daily[-1]['date'] if daily else '',
            **summary,
            'avg_daily_unique_traders': sum(unique_trader_values) / len(unique_trader_values) if unique_trader_values else 0.0,
            'max_daily_unique_traders': max(unique_trader_values) if unique_trader_values else 0.0,
            'total_unique_traders': float(total_unique_traders),
            'total_unique_trader_days': total_unique_trader_days,
            'pairs': dict(pair_summary),
            'close_reasons': dict(close_reason_summary),
        }

    async def get_infographic_data(
        self,
        days: int = 7,
        end_ts: int | None = None,
        top_pairs_count: int = 10,
    ) -> LimitSwapPeriodStats:
        """
        Collect limit-swap statistics into a typed LimitSwapPeriodStats object
        ready for infographic rendering and Telegram notification.
        """
        await self._ensure_runtime_resources()
        end_ts = int(end_ts or now_ts())
        prev_end_ts = end_ts - days * DAY

        # ── daily snapshots ───────────────────────────────────────────────
        current_daily, prev_daily = await asyncio.gather(
            self.get_daily_data(days=days, end_ts=end_ts),
            self.get_daily_data(days=days, end_ts=prev_end_ts),
        )

        # ── aggregate helper ──────────────────────────────────────────────
        def _aggregate(daily_data):
            totals = {'opened_count': 0.0, 'opened_usd': 0.0}
            pair_totals = defaultdict(lambda: {'opened_count': 0.0, 'opened_usd': 0.0})
            for day in daily_data:
                totals['opened_count'] += day.get('opened_count', 0.0)
                totals['opened_usd'] += day.get('opened_usd', 0.0)
                for pair_name, pd in day.get('pairs', {}).items():
                    pair_totals[pair_name]['opened_count'] += pd.get('opened_count', 0.0)
                    pair_totals[pair_name]['opened_usd'] += pd.get('opened_usd', 0.0)
            return totals, dict(pair_totals)

        curr_totals, curr_pair_totals = _aggregate(current_daily)
        prev_totals, _ = _aggregate(prev_daily)

        # ── HyperLogLog unique traders (true cross-day uniqueness) ────────
        curr_unique, prev_unique = await asyncio.gather(
            self.get_unique_traders(days=days, end_ts=end_ts),
            self.get_unique_traders(days=days, end_ts=prev_end_ts),
        )
        curr_totals['unique_traders'] = float(curr_unique)
        prev_totals['unique_traders'] = float(prev_unique)

        # ── delta calculation ─────────────────────────────────────────────
        def _pct(c: float, p: float) -> float:
            return round((c - p) / p * 100.0, 2) if p else 0.0

        def _make_delta(key: str) -> LimitSwapDelta:
            c, p = curr_totals[key], prev_totals.get(key, 0.0)
            return LimitSwapDelta(absolute=round(c - p, 4), pct=_pct(c, p))

        # ── per-day chart data ────────────────────────────────────────────
        daily_points = [
            LimitSwapDailyPoint(
                date=d['date'],
                opened_count=int(d.get('opened_count', 0.0)),
                opened_usd=round(float(d.get('opened_usd', 0.0)), 2),
                unique_traders=int(d.get('unique_traders', 0.0)),
            )
            for d in current_daily
        ]

        # ── top pairs ─────────────────────────────────────────────────────
        pair_names = list(curr_pair_totals.keys())
        pair_unique_list = await asyncio.gather(
            *[self.get_pair_unique_traders(p, days=days, end_ts=end_ts) for p in pair_names]
        ) if pair_names else []
        pair_unique = dict(zip(pair_names, pair_unique_list))

        top_pairs = sorted(
            [
                LimitSwapPairStats(
                    pair=pair_name,
                    opened_count=int(curr_pair_totals[pair_name]['opened_count']),
                    opened_usd=round(curr_pair_totals[pair_name]['opened_usd'], 2),
                    unique_traders=pair_unique.get(pair_name, 0),
                )
                for pair_name in curr_pair_totals
            ],
            key=lambda x: x.opened_count,
            reverse=True,
        )[:top_pairs_count]

        # ── assemble result ───────────────────────────────────────────────
        return LimitSwapPeriodStats(
            period_days=days,
            start_date=current_daily[0]['date'] if current_daily else '',
            end_date=current_daily[-1]['date'] if current_daily else '',
            total=LimitSwapTotals(
                opened_count=int(curr_totals['opened_count']),
                opened_usd=round(curr_totals['opened_usd'], 2),
                unique_traders=int(curr_totals['unique_traders']),
            ),
            previous=LimitSwapTotals(
                opened_count=int(prev_totals['opened_count']),
                opened_usd=round(prev_totals['opened_usd'], 2),
                unique_traders=int(prev_totals['unique_traders']),
            ),
            delta=LimitSwapDeltas(
                opened_count=_make_delta('opened_count'),
                opened_usd=_make_delta('opened_usd'),
                unique_traders=_make_delta('unique_traders'),
            ),
            daily=daily_points,
            top_pairs=top_pairs,
        )

    @staticmethod
    def _event_fingerprint(ev: ThorEvent) -> str:
        return json.dumps(ev.attrs or {}, sort_keys=True, default=str)

    async def _ensure_runtime_resources(self):
        await self.deps.db.get_redis()
        if self._opened_dedup is None:
            self._opened_dedup = TxDeduplicator(self.deps.db, 'LimitSwap:opened')
        if self._partial_dedup is None:
            self._partial_dedup = TxDeduplicator(self.deps.db, 'LimitSwap:partial')
        if self._closed_dedup is None:
            self._closed_dedup = TxDeduplicator(self.deps.db, 'LimitSwap:closed')
        if self._trader_counter is None:
            self._trader_counter = DailyActiveUserCounter(self.deps.db.redis, 'LimitSwapTraders')
        else:
            self._trader_counter.r = self.deps.db.redis

    async def _save_open_meta(self, meta: OpenLimitSwapMeta):
        r = await self.deps.db.get_redis()
        await r.hset(self.OPEN_META_KEY, meta.tx_hash, meta.to_json())

    async def _load_open_meta(self, tx_hash: str) -> Optional[OpenLimitSwapMeta]:
        if not tx_hash:
            return None
        r = await self.deps.db.get_redis()
        raw = await r.hget(self.OPEN_META_KEY, tx_hash)
        return OpenLimitSwapMeta.from_json(raw)

    async def _delete_open_meta(self, tx_hash: str):
        if not tx_hash:
            return
        r = await self.deps.db.get_redis()
        await r.hdel(self.OPEN_META_KEY, tx_hash)

    async def clean_old_open_meta(self, older_than_ts: int | None = None) -> int:
        """
        Remove stale or malformed cached open-limit metadata.

        Entries are considered stale when their saved timestamp is older than the
        retention cutoff. Malformed payloads are deleted as well.
        """
        r = await self.deps.db.get_redis()
        cutoff_ts = int(older_than_ts or (now_ts() - self.OPEN_META_RETENTION_SEC))
        raw_items = await r.hgetall(self.OPEN_META_KEY)
        to_delete = []

        for tx_hash, raw in raw_items.items():
            meta = OpenLimitSwapMeta.from_json(raw)
            if not meta:
                to_delete.append(tx_hash)
                continue
            if meta.timestamp <= 0 or meta.timestamp < cutoff_ts:
                to_delete.append(tx_hash)

        if to_delete:
            await r.hdel(self.OPEN_META_KEY, *to_delete)
        return len(to_delete)

    @async_once_every(OPEN_META_CLEAN_EVERY_N_UPDATES)
    async def _clean_open_meta_occasionally(self):
        n_deleted = await self.clean_old_open_meta()
        if n_deleted:
            self.logger.info(f'Cleaned {n_deleted} stale limit swap open-meta entries')

    @staticmethod
    def _extract_close_tx_hash(item: ClosedLimitSwap) -> str:
        ev = item.event
        attrs = ev.attrs if isinstance(ev.attrs, dict) else {}
        return str(attrs.get('id') or attrs.get('tx_id') or attrs.get('in_tx_id') or attrs.get('hash') or '')

    @staticmethod
    def _extract_tx_signer(tx: NativeThorTx) -> str:
        for message in tx.messages:
            if signer := message.get('signer', ''):
                return str(signer)
            if from_address := message.get('from_address', ''):
                return str(from_address)
        return str(tx.first_signer_address or '')

    @staticmethod
    def _extract_first_coin(tx: NativeThorTx):
        for message in tx.messages:
            if message.type == ThorTxMessage.MsgDeposit and message.coins:
                coin = message.coins[0]
                return coin.get('asset', ''), int(coin.get('amount', 0))

            if message.is_send:
                amounts = message.get('amount', [])
                if amounts:
                    coin = amounts[0]
                    asset = coin.get('asset') or coin.get('denom', '')
                    return asset, int(coin.get('amount', 0))

        return '', 0

    @staticmethod
    def _normalize_asset_name(asset: str) -> str:
        if not asset:
            return ''
        if is_rune(asset):
            return 'THOR.RUNE'
        try:
            return str(Asset.from_string(asset))
        except Exception:
            return str(asset)

    def _price_coin_usd(self, ph, asset: str, amount: int) -> float:
        if not asset or amount <= 0:
            return 0.0

        asset = self._normalize_asset_name(asset)
        amount_float = thor_to_float(amount)

        if is_rune(asset):
            return amount_float * ph.usd_per_rune

        try:
            in_asset = Asset.from_string(asset)
            pool_name = ph.pool_fuzzy_first(in_asset.native_pool_name, restore_type=True) or in_asset.native_pool_name
            pool = ph.find_pool(pool_name)
            usd_per_asset = getattr(pool, 'usd_per_asset', 0.0) if pool else 0.0
            if not usd_per_asset:
                usd_per_asset = ph.usd_per_asset(pool_name) or 0.0
            return amount_float * float(usd_per_asset or 0.0)
        except Exception as e:
            self.logger.warning(f'Failed to price asset {asset}: {e!r}')
            return 0.0

    def _build_open_meta(self, tx: NativeThorTx, fallback_ts: int, ph) -> Optional[OpenLimitSwapMeta]:
        parsed = THORMemo.parse_memo(tx.memo or '', no_raise=True)
        if not parsed or parsed.action != ActionType.LIMIT_ORDER:
            return None

        source_asset, source_amount = self._extract_first_coin(tx)
        source_asset = self._normalize_asset_name(source_asset)
        target_asset = self._normalize_asset_name(parsed.asset)
        if not source_asset or not target_asset:
            self.logger.warning(f'Cannot derive pair for limit swap {tx.tx_hash}: {tx.memo!r}')
            return None

        return OpenLimitSwapMeta(
            tx_hash=str(tx.tx_hash),
            block_no=int(tx.height or 0),
            timestamp=int(tx.timestamp or fallback_ts or now_ts()),
            source_asset=source_asset,
            target_asset=target_asset,
            usd_amount=self._price_coin_usd(ph, source_asset, source_amount),
            trader=self._extract_tx_signer(tx),
        )

    def _build_partial_usd(self, ev: ThorEvent, ph) -> float:
        try:
            swap = EventSwap.from_event(ev)
            return self._price_coin_usd(ph, swap.asset, swap.amount)
        except Exception as e:
            self.logger.warning(f'Failed to price partial limit swap event: {e!r}')
            return 0.0

    async def _update_unique_traders_snapshot(self, traders: set[str], ts: int):
        traders = {t for t in traders if t}
        if not traders:
            return
        await self._trader_counter.hit(users=traders, now=float(ts))
        current_dau = await self._trader_counter.get_dau(float(ts))
        await self.accumulator.set(ts, unique_traders=current_dau)

    def _get_pair_trader_counter(self, canonical_pair_name: str) -> DailyActiveUserCounter:
        """Return (or lazily create) a per-pair DailyActiveUserCounter using HyperLogLog."""
        slug = self._slug(canonical_pair_name)
        if slug not in self._pair_trader_counters:
            self._pair_trader_counters[slug] = DailyActiveUserCounter(
                self.deps.db.redis, f'LimitSwapPairTraders:{slug}'
            )
        else:
            # Keep the Redis connection reference current.
            self._pair_trader_counters[slug].r = self.deps.db.redis
        return self._pair_trader_counters[slug]

    async def _process_opened(self, data: LimitSwapBlockUpdate, ph):
        tx_map = {tx.tx_hash: tx for tx in data.new_opened_limit_swaps if tx and tx.tx_hash}
        new_hashes = await self._opened_dedup.only_new_hashes(list(tx_map.keys()))
        traders = set()
        pair_traders: dict[str, set[str]] = defaultdict(set)

        for tx_hash in new_hashes:
            tx = tx_map.get(tx_hash)
            if not tx:
                continue
            meta = self._build_open_meta(tx, data.timestamp, ph)
            if not meta:
                continue

            traders.add(meta.trader)
            canonical_name = self._pair_canonical_name(meta.source_asset, meta.target_asset)
            if meta.trader:
                pair_traders[canonical_name].add(meta.trader)

            await self.accumulator.add(
                meta.timestamp,
                opened_count=1,
                opened_usd=meta.usd_amount,
                **{
                    self._pair_count_key(meta.source_asset, meta.target_asset): 1,
                    self._pair_usd_key(meta.source_asset, meta.target_asset): meta.usd_amount,
                }
            )
            await self._save_open_meta(meta)
            await self._opened_dedup.mark_as_seen(tx_hash)

        ts = data.timestamp or now_ts()

        # Update HyperLogLog and snapshot unique-trader count per pair.
        for canonical_name, pair_trader_set in pair_traders.items():
            counter = self._get_pair_trader_counter(canonical_name)
            await counter.hit(users=pair_trader_set, now=float(ts))
            dau = await counter.get_dau(float(ts))
            await self.accumulator.set(ts, **{f'pair:{canonical_name}:unique_traders': dau})

        await self._update_unique_traders_snapshot(traders, ts)

    async def _process_partials(self, data: LimitSwapBlockUpdate, ph):
        fp_map = {self._event_fingerprint(ev): ev for ev in data.partial_swaps}
        new_fingerprints = await self._partial_dedup.only_new_hashes(list(fp_map.keys()))

        for fp in new_fingerprints:
            ev = fp_map.get(fp)
            if not ev:
                continue
            usd_amount = self._build_partial_usd(ev, ph)
            await self.accumulator.add(
                data.timestamp or now_ts(),
                partial_count=1,
                partial_usd=usd_amount,
            )
            await self._partial_dedup.mark_as_seen(fp)

    async def _process_closed(self, data: LimitSwapBlockUpdate):
        fp_map = {self._event_fingerprint(item.event): item for item in data.closed_limit_swaps}
        new_fingerprints = await self._closed_dedup.only_new_hashes(list(fp_map.keys()))
        ts = data.timestamp or now_ts()
        touched_duration = False

        for fp in new_fingerprints:
            item = fp_map.get(fp)
            if not item:
                continue

            fields = {
                'closed_count': 1,
                self._close_reason_key(item.reason): 1,
            }

            tx_hash = self._extract_close_tx_hash(item)
            meta = await self._load_open_meta(tx_hash)
            if meta and data.block_no and meta.block_no:
                duration_blocks = max(0, int(data.block_no) - int(meta.block_no))
                fields['closed_duration_blocks_sum'] = duration_blocks
                fields['closed_duration_samples'] = 1
                touched_duration = True
                await self._delete_open_meta(tx_hash)

            await self.accumulator.add(ts, **fields)
            await self._closed_dedup.mark_as_seen(fp)

        if touched_duration:
            current = await self.accumulator.get(ts)
            duration_sum = current.get('closed_duration_blocks_sum', 0.0)
            duration_samples = current.get('closed_duration_samples', 0.0)
            avg_duration = duration_sum / duration_samples if duration_samples else 0.0
            await self.accumulator.set(ts, avg_duration_blocks=avg_duration)

    async def on_data(self, sender, data: LimitSwapBlockUpdate):
        await self._ensure_runtime_resources()
        ph = await self.deps.pool_cache.get()

        await self._process_opened(data, ph)
        await self._process_partials(data, ph)
        await self._process_closed(data)
        await self._clean_open_meta_occasionally()
