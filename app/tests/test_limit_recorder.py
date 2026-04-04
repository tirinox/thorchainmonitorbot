from collections import defaultdict
from datetime import datetime
from typing import cast

import pytest

from jobs.limit_recorder import LimitSwapStatsRecorder, OpenLimitSwapMeta
from jobs.scanner.limit_detector import LimitSwapBlockUpdate, ClosedLimitSwap, OpenedLimitSwap
from jobs.scanner.tx import ThorEvent
from lib.db import DB
from lib.depcont import DepContainer
from models.pool_info import PoolInfo
from models.price import PriceHolder


class FakeRedis:
    def __init__(self):
        self.hashes = defaultdict(dict)
        self.hll = defaultdict(set)

    async def hincrbyfloat(self, name, key, value):
        bucket = self.hashes[name]
        bucket[key] = float(bucket.get(key, 0.0)) + float(value)
        return bucket[key]

    async def hset(self, name, *args, mapping=None):
        bucket = self.hashes[name]
        if mapping is not None:
            for k, v in mapping.items():
                bucket[k] = v
            return len(mapping)
        if len(args) == 2:
            field, value = args
            bucket[field] = value
            return 1
        raise TypeError("Unsupported hset call")

    async def hget(self, name, field):
        return self.hashes.get(name, {}).get(field)

    async def hgetall(self, name):
        bucket = self.hashes.get(name, {})
        return {
            k: (str(v) if isinstance(v, (int, float)) else v)
            for k, v in bucket.items()
        }

    async def hdel(self, name, *fields):
        bucket = self.hashes.get(name, {})
        deleted = 0
        for field in fields:
            if field in bucket:
                del bucket[field]
                deleted += 1
        return deleted

    async def pfadd(self, name, *values):
        self.hll[name].update(str(v) for v in values)
        return 1

    async def pfcount(self, *names):
        combined = set()
        for name in names:
            combined.update(self.hll.get(name, set()))
        return len(combined)

    async def delete(self, *names):
        for name in names:
            self.hashes.pop(name, None)
            self.hll.pop(name, None)


class FakeDB:
    def __init__(self):
        self.redis = FakeRedis()

    async def get_redis(self):
        return self.redis


class FakeDedup:
    def __init__(self, db, key, *args, **kwargs):
        self.seen = set()
        self.key = key

    async def only_new_hashes(self, hashes):
        return [h for h in hashes if h and h not in self.seen]

    async def mark_as_seen(self, tx_id):
        if tx_id:
            self.seen.add(tx_id)


class FakePoolCache:
    def __init__(self, ph):
        self._ph = ph

    async def get(self):
        return self._ph


def make_price_holder():
    ph = PriceHolder(stable_coins=['THOR.RUNE'])
    ph.usd_per_rune = 2.0
    ph.pool_info_map = {
        'BTC.BTC': PoolInfo('BTC.BTC', balance_asset=100_000_000, balance_rune=1_500_000_000_000,
                            pool_units=1, status=PoolInfo.AVAILABLE, usd_per_asset=30_000.0),
        'ETH.ETH': PoolInfo('ETH.ETH', balance_asset=1_000_000_000, balance_rune=1_000_000_000_000,
                            pool_units=1, status=PoolInfo.AVAILABLE, usd_per_asset=2_000.0),
    }
    return ph


def make_opened_limit_swap(
    tx_id: str,
    memo: str,
    source_asset: str,
    source_amount: int,
    source_amount_float: float,
    trader: str,
    target_asset: str,
    source_decimals: int = 8,
    thor_block_no: int = 0,
):
    return OpenedLimitSwap(
        tx_id=tx_id,
        memo=memo,
        source_asset=source_asset,
        source_amount=source_amount,
        source_amount_float=source_amount_float,
        source_decimals=source_decimals,
        trader=trader,
        target_asset=target_asset,
        thor_block_no=thor_block_no,
    )


def make_event(ev_type: str, **attrs):
    data = {'type': ev_type, **attrs}
    return ThorEvent.from_dict(data, height=int(attrs.get('_height', 0) or 0))


@pytest.mark.asyncio
async def test_limit_recorder_daily_stats(monkeypatch):
    import jobs.limit_recorder as limit_recorder_module

    monkeypatch.setattr(limit_recorder_module, 'EventDbTxDeduplicator', FakeDedup)

    deps = DepContainer()
    deps.db = cast(DB, cast(object, FakeDB()))
    deps.pool_cache = FakePoolCache(make_price_holder())

    recorder = LimitSwapStatsRecorder(deps)

    day1 = 1_700_000_000
    day2 = day1 + 86_400

    tx1 = make_opened_limit_swap(
        tx_id='open-1',
        memo='=<:ETH.ETH:thor1dest:2500000000/100800/0',
        source_asset='BTC.BTC',
        source_amount=100_000_000,
        source_amount_float=1.0,
        trader='thor1alice',
        target_asset='ETH.ETH',
        thor_block_no=100,
    )
    tx2 = make_opened_limit_swap(
        tx_id='open-2',
        memo='=<:BTC.BTC:thor1dest:100000000/100800/0',
        source_asset='ETH.ETH',
        source_amount=100_000_000,
        source_amount_float=1.0,
        trader='thor1bob',
        target_asset='BTC.BTC',
        thor_block_no=101,
    )

    opened_update = LimitSwapBlockUpdate(
        block_no=101,
        timestamp=day1,
        new_opened_limit_swaps=[tx1, tx2],
        closed_limit_swaps=[],
        partial_swaps=[],
    )

    await recorder.on_data(None, opened_update)
    # Repeat exact same batch; dedup should prevent double counting.
    await recorder.on_data(None, opened_update)

    day1_stats = await recorder.accumulator.get(day1)
    assert day1_stats['opened_count'] == 2.0
    assert day1_stats['opened_usd'] == 32_000.0
    assert day1_stats['unique_traders'] == 2.0
    assert day1_stats['pair:BTC.BTC->ETH.ETH:opened_count'] == 2.0
    assert day1_stats['pair:BTC.BTC->ETH.ETH:opened_usd'] == 32_000.0

    partial = make_event(
        'swap',
        memo='=<:ETH.ETH:thor1dest:2500000000/100800/0',
        id='open-1',
        asset='BTC.BTC',
        amount='50000000',
    )
    close = make_event(
        'limit_swap_close',
        reason='limit swap expired',
        id='open-1',
    )

    close_update = LimitSwapBlockUpdate(
        block_no=110,
        timestamp=day2,
        new_opened_limit_swaps=[],
        closed_limit_swaps=[ClosedLimitSwap(close, 'limit swap expired')],
        partial_swaps=[partial],
    )

    await recorder.on_data(None, close_update)
    # Repeat exact same close/partial batch; dedup should prevent double counting.
    await recorder.on_data(None, close_update)

    day2_stats = await recorder.accumulator.get(day2)
    assert day2_stats['partial_count'] == 1.0
    assert day2_stats['partial_usd'] == 15_000.0
    assert day2_stats['closed_count'] == 1.0
    assert day2_stats['closed_reason:limit_swap_expired'] == 1.0
    assert day2_stats['closed_duration_blocks_sum'] == 10.0
    assert day2_stats['closed_duration_samples'] == 1.0
    assert day2_stats['avg_duration_blocks'] == 10.0

    meta_after_close = await recorder._load_open_meta('open-1')
    assert meta_after_close is None


@pytest.mark.asyncio
async def test_clean_old_open_meta_removes_stale_and_malformed(monkeypatch):
    import jobs.limit_recorder as limit_recorder_module

    monkeypatch.setattr(limit_recorder_module, 'EventDbTxDeduplicator', FakeDedup)

    deps = DepContainer()
    deps.db = cast(DB, cast(object, FakeDB()))
    deps.pool_cache = FakePoolCache(make_price_holder())

    recorder = LimitSwapStatsRecorder(deps)

    old_ts = 1_700_000_000
    cutoff = old_ts + 10

    await recorder._save_open_meta(OpenLimitSwapMeta(
        tx_hash='old-open',
        block_no=100,
        timestamp=old_ts,
        source_asset='BTC.BTC',
        target_asset='ETH.ETH',
        usd_amount=1.0,
        trader='thor1old',
    ))
    await deps.db.redis.hset(recorder.OPEN_META_KEY, 'broken-open', '{not-json')
    await recorder._save_open_meta(OpenLimitSwapMeta(
        tx_hash='fresh-open',
        block_no=101,
        timestamp=cutoff,
        source_asset='ETH.ETH',
        target_asset='BTC.BTC',
        usd_amount=2.0,
        trader='thor1fresh',
    ))

    deleted = await recorder.clean_old_open_meta(older_than_ts=cutoff)
    assert deleted == 2
    assert await recorder._load_open_meta('old-open') is None
    assert await recorder._load_open_meta('broken-open') is None

    fresh = await recorder._load_open_meta('fresh-open')
    assert fresh is not None
    assert fresh.tx_hash == 'fresh-open'


@pytest.mark.asyncio
async def test_get_daily_data_and_summary(monkeypatch):
    import jobs.limit_recorder as limit_recorder_module

    monkeypatch.setattr(limit_recorder_module, 'EventDbTxDeduplicator', FakeDedup)

    deps = DepContainer()
    deps.db = cast(DB, cast(object, FakeDB()))
    deps.pool_cache = FakePoolCache(make_price_holder())

    recorder = LimitSwapStatsRecorder(deps)

    day1 = 1_700_000_000
    day2 = day1 + 86_400

    tx1 = make_opened_limit_swap(
        tx_id='open-1',
        memo='=<:ETH.ETH:thor1dest:2500000000/100800/0',
        source_asset='BTC.BTC',
        source_amount=100_000_000,
        source_amount_float=1.0,
        trader='thor1alice',
        target_asset='ETH.ETH',
        thor_block_no=100,
    )
    tx2 = make_opened_limit_swap(
        tx_id='open-2',
        memo='=<:BTC.BTC:thor1dest:100000000/100800/0',
        source_asset='ETH.ETH',
        source_amount=100_000_000,
        source_amount_float=1.0,
        trader='thor1bob',
        target_asset='BTC.BTC',
        thor_block_no=101,
    )

    await recorder.on_data(None, LimitSwapBlockUpdate(
        block_no=101,
        timestamp=day1,
        new_opened_limit_swaps=[tx1, tx2],
        closed_limit_swaps=[],
        partial_swaps=[],
    ))

    partial = make_event(
        'swap',
        memo='=<:ETH.ETH:thor1dest:2500000000/100800/0',
        id='open-1',
        asset='BTC.BTC',
        amount='50000000',
    )
    close = make_event(
        'limit_swap_close',
        reason='limit swap expired',
        id='open-1',
    )

    await recorder.on_data(None, LimitSwapBlockUpdate(
        block_no=110,
        timestamp=day2,
        new_opened_limit_swaps=[],
        closed_limit_swaps=[ClosedLimitSwap(close, 'limit swap expired')],
        partial_swaps=[partial],
    ))

    daily = await recorder.get_daily_data(days=2, end_ts=day2)
    assert len(daily) == 2

    d1 = daily[0]
    d2 = daily[1]
    assert d1['date'] == datetime.fromtimestamp(day1).strftime('%Y-%m-%d')
    assert d2['date'] == datetime.fromtimestamp(day2).strftime('%Y-%m-%d')

    assert d1['opened_count'] == 2.0
    assert d1['opened_usd'] == 32_000.0
    assert d1['unique_traders'] == 2.0
    assert d1['pairs']['BTC.BTC->ETH.ETH']['opened_count'] == 2.0
    assert d1['pairs']['BTC.BTC->ETH.ETH']['opened_usd'] == 32_000.0
    assert d1['close_reasons'] == {}

    assert d2['partial_count'] == 1.0
    assert d2['partial_usd'] == 15_000.0
    assert d2['closed_count'] == 1.0
    assert d2['avg_duration_blocks'] == 10.0
    assert d2['close_reasons']['limit_swap_expired'] == 1.0

    summary = await recorder.get_summary(days=2, end_ts=day2)
    assert summary['days'] == 2
    assert summary['start_date'] == d1['date']
    assert summary['end_date'] == d2['date']
    assert summary['opened_count'] == 2.0
    assert summary['opened_usd'] == 32_000.0
    assert summary['partial_count'] == 1.0
    assert summary['partial_usd'] == 15_000.0
    assert summary['closed_count'] == 1.0
    assert summary['closed_duration_blocks_sum'] == 10.0
    assert summary['closed_duration_samples'] == 1.0
    assert summary['avg_duration_blocks'] == 10.0
    assert summary['unique_traders'] == 2.0
    assert summary['total_unique_traders'] == 2.0
    assert summary['avg_daily_unique_traders'] == 1.0
    assert summary['max_daily_unique_traders'] == 2.0
    assert summary['total_unique_trader_days'] == 2.0
    assert summary['pairs']['BTC.BTC->ETH.ETH']['opened_usd'] == 32_000.0
    assert summary['pairs']['BTC.BTC->ETH.ETH']['opened_count'] == 2.0
    assert summary['close_reasons']['limit_swap_expired'] == 1.0


@pytest.mark.asyncio
async def test_get_summary_uses_hll_for_cross_day_unique_traders(monkeypatch):
    import jobs.limit_recorder as limit_recorder_module

    monkeypatch.setattr(limit_recorder_module, 'EventDbTxDeduplicator', FakeDedup)

    deps = DepContainer()
    deps.db = cast(DB, cast(object, FakeDB()))
    deps.pool_cache = FakePoolCache(make_price_holder())

    recorder = LimitSwapStatsRecorder(deps)

    day1 = 1_700_000_000
    day2 = day1 + 86_400

    tx1 = make_opened_limit_swap(
        tx_id='open-a',
        memo='=<:ETH.ETH:thor1dest:2500000000/100800/0',
        source_asset='BTC.BTC',
        source_amount=100_000_000,
        source_amount_float=1.0,
        trader='thor1same',
        target_asset='ETH.ETH',
        thor_block_no=100,
    )
    tx2 = make_opened_limit_swap(
        tx_id='open-b',
        memo='=<:BTC.BTC:thor1dest:100000000/100800/0',
        source_asset='ETH.ETH',
        source_amount=100_000_000,
        source_amount_float=1.0,
        trader='thor1same',
        target_asset='BTC.BTC',
        thor_block_no=101,
    )

    await recorder.on_data(None, LimitSwapBlockUpdate(
        block_no=100,
        timestamp=day1,
        new_opened_limit_swaps=[tx1],
        closed_limit_swaps=[],
        partial_swaps=[],
    ))
    await recorder.on_data(None, LimitSwapBlockUpdate(
        block_no=101,
        timestamp=day2,
        new_opened_limit_swaps=[tx2],
        closed_limit_swaps=[],
        partial_swaps=[],
    ))

    daily = await recorder.get_daily_data(days=2, end_ts=day2)
    assert daily[0]['unique_traders'] == 1.0
    assert daily[1]['unique_traders'] == 1.0

    summary = await recorder.get_summary(days=2, end_ts=day2)
    assert summary['total_unique_trader_days'] == 2.0
    assert summary['unique_traders'] == 1.0
    assert summary['total_unique_traders'] == 1.0


@pytest.mark.asyncio
async def test_get_infographic_data_sorts_top_pairs_by_volume(monkeypatch):
    import jobs.limit_recorder as limit_recorder_module

    monkeypatch.setattr(limit_recorder_module, 'EventDbTxDeduplicator', FakeDedup)

    deps = DepContainer()
    deps.db = cast(DB, cast(object, FakeDB()))
    deps.pool_cache = FakePoolCache(make_price_holder())

    recorder = LimitSwapStatsRecorder(deps)

    day1 = 1_700_000_000

    high_volume_pair = make_opened_limit_swap(
        tx_id='open-btc-rune',
        memo='=<:THOR.RUNE:thor1dest:100000000/100800/0',
        source_asset='BTC.BTC',
        source_amount=100_000_000,
        source_amount_float=1.0,
        trader='thor1btc',
        target_asset='THOR.RUNE',
    )
    lower_volume_pair_1 = make_opened_limit_swap(
        tx_id='open-eth-rune-1',
        memo='=<:THOR.RUNE:thor1dest:100000000/100800/0',
        source_asset='ETH.ETH',
        source_amount=100_000_000,
        source_amount_float=1.0,
        trader='thor1eth1',
        target_asset='THOR.RUNE',
    )
    lower_volume_pair_2 = make_opened_limit_swap(
        tx_id='open-eth-rune-2',
        memo='=<:THOR.RUNE:thor1dest:100000000/100800/0',
        source_asset='ETH.ETH',
        source_amount=100_000_000,
        source_amount_float=1.0,
        trader='thor1eth2',
        target_asset='THOR.RUNE',
    )

    await recorder.on_data(None, LimitSwapBlockUpdate(
        block_no=102,
        timestamp=day1,
        new_opened_limit_swaps=[high_volume_pair, lower_volume_pair_1, lower_volume_pair_2],
        closed_limit_swaps=[],
        partial_swaps=[],
    ))

    stats = await recorder.get_infographic_data(days=1, end_ts=day1)

    assert [pair.pair for pair in stats.top_pairs] == [
        'BTC.BTC->THOR.RUNE',
        'ETH.ETH->THOR.RUNE',
    ]
    assert stats.top_pairs[0].opened_usd == 30_000.0
    assert stats.top_pairs[0].opened_count == 1
    assert stats.top_pairs[1].opened_usd == 4_000.0
    assert stats.top_pairs[1].opened_count == 2


@pytest.mark.asyncio
async def test_get_daily_data_default_14_days(monkeypatch):
    import jobs.limit_recorder as limit_recorder_module

    monkeypatch.setattr(limit_recorder_module, 'EventDbTxDeduplicator', FakeDedup)

    fixed_now = 1_700_000_000
    monkeypatch.setattr(limit_recorder_module, 'now_ts', lambda: fixed_now)

    deps = DepContainer()
    deps.db = cast(DB, cast(object, FakeDB()))
    deps.pool_cache = FakePoolCache(make_price_holder())

    recorder = LimitSwapStatsRecorder(deps)
    daily = await recorder.get_daily_data()

    assert len(daily) == 14
    assert daily[-1]['date'] == datetime.fromtimestamp(fixed_now).strftime('%Y-%m-%d')
    assert all(day['opened_count'] == 0.0 for day in daily)


@pytest.mark.asyncio
async def test_closed_limit_dedup_uses_tx_id(monkeypatch):
    import jobs.limit_recorder as limit_recorder_module

    monkeypatch.setattr(limit_recorder_module, 'EventDbTxDeduplicator', FakeDedup)

    deps = DepContainer()
    deps.db = cast(DB, cast(object, FakeDB()))
    deps.pool_cache = FakePoolCache(make_price_holder())

    recorder = LimitSwapStatsRecorder(deps)

    day1 = 1_700_000_000
    day2 = day1 + 86_400

    tx1 = make_opened_limit_swap(
        tx_id='open-1',
        memo='=<:ETH.ETH:thor1dest:2500000000/100800/0',
        source_asset='BTC.BTC',
        source_amount=100_000_000,
        source_amount_float=1.0,
        trader='thor1alice',
        target_asset='ETH.ETH',
        thor_block_no=100,
    )

    await recorder.on_data(None, LimitSwapBlockUpdate(
        block_no=101,
        timestamp=day1,
        new_opened_limit_swaps=[tx1],
        closed_limit_swaps=[],
        partial_swaps=[],
    ))

    close1 = make_event(
        'limit_swap_close',
        reason='limit swap expired',
        id='open-1',
    )
    close2 = make_event(
        'limit_swap_close',
        reason='limit swap cancelled',
        id='open-1',
        extra_field='same-close-different-payload',
    )

    await recorder.on_data(None, LimitSwapBlockUpdate(
        block_no=110,
        timestamp=day2,
        new_opened_limit_swaps=[],
        closed_limit_swaps=[
            ClosedLimitSwap(close1, 'limit swap expired'),
            ClosedLimitSwap(close2, 'limit swap cancelled'),
        ],
        partial_swaps=[],
    ))

    day2_stats = await recorder.accumulator.get(day2)
    assert day2_stats['closed_count'] == 1.0
    assert day2_stats['closed_duration_blocks_sum'] == 10.0
    assert day2_stats['closed_duration_samples'] == 1.0


@pytest.mark.asyncio
async def test_opened_observed_limit_swap_uses_amount_float_for_usd_pricing(monkeypatch):
    import jobs.limit_recorder as limit_recorder_module

    monkeypatch.setattr(limit_recorder_module, 'EventDbTxDeduplicator', FakeDedup)

    deps = DepContainer()
    deps.db = cast(DB, cast(object, FakeDB()))
    deps.pool_cache = FakePoolCache(make_price_holder())

    recorder = LimitSwapStatsRecorder(deps)

    day1 = 1_700_000_000
    observed_open = make_opened_limit_swap(
        tx_id='observed-open-1',
        memo='=<:BTC.BTC:bc1qfoo:1000000/100800/0',
        source_asset='ETH.ETH',
        source_amount=2,
        source_amount_float=2.0,
        source_decimals=0,
        trader='0xobserved',
        target_asset='BTC.BTC',
    )

    await recorder.on_data(None, LimitSwapBlockUpdate(
        block_no=500,
        timestamp=day1,
        new_opened_limit_swaps=[observed_open],
        closed_limit_swaps=[],
        partial_swaps=[],
    ))

    day1_stats = await recorder.accumulator.get(day1)
    assert day1_stats['opened_count'] == 1.0
    assert day1_stats['opened_usd'] == 4_000.0
    assert day1_stats['pair:BTC.BTC->ETH.ETH:opened_usd'] == 4_000.0


