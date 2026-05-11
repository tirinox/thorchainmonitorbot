from typing import cast

import pytest

from jobs.rapid_recorder import RapidSwapRecorder
from jobs.scanner.block_result import BlockResult, ScannerError
from jobs.scanner.tx import ThorEvent
from lib.db import DB
from lib.depcont import DepContainer
from tests.fakes import FakeDB, FakePoolCache, FakeRedis, make_price_holder


def make_deps() -> DepContainer:
    deps = DepContainer()
    deps.db = cast(DB, cast(object, FakeDB(FakeRedis())))
    deps.pool_cache = FakePoolCache(make_price_holder(include_rune=True))
    return deps


def make_lazy_db_deps() -> DepContainer:
    deps = DepContainer()
    deps.db = cast(DB, cast(object, FakeDB(lazy=True)))
    deps.pool_cache = FakePoolCache(make_price_holder(include_rune=True))
    return deps


def make_swap_event(
    tx_id: str,
    height: int,
    pool: str = 'BTC.BTC',
    *,
    coin: str = '100000000 BTC.BTC',
    from_addr: str = 'thor1from',
    stream_count: int = 1,
    stream_quantity: int = 1,
):
    return ThorEvent.from_dict({
        'type': 'swap',
        'id': tx_id,
        'pool': pool,
        'swap_target': '0',
        'swap_slip': '0',
        'liquidity_fee': '0',
        'liquidity_fee_in_rune': '0',
        'emit_asset': '1 THOR.RUNE',
        'streaming_swap_quantity': str(stream_quantity),
        'streaming_swap_count': str(stream_count),
        'chain': 'THOR',
        'from': from_addr,
        'to': 'thor1to',
        'coin': coin,
        'memo': 'SWAP:THOR.RUNE:thor1to',
    }, height=height)


def make_outbound_event(tx_id: str, height: int):
    return ThorEvent.from_dict({
        'type': 'outbound',
        'in_tx_id': tx_id,
        'id': f'out-{tx_id}',
        'chain': 'BTC',
        'from': 'thor1module',
        'to': 'bc1dest',
        'coin': '1 BTC.BTC',
        'memo': f'OUT:{tx_id}',
    }, height=height)


def make_block(*events, block_no: int = 123, timestamp: int = 1_700_000_000):
    return BlockResult(
        block_no=block_no,
        txs=[],
        end_block_events=list(events),
        begin_block_events=[],
        error=ScannerError(0, ''),
        timestamp=timestamp,
    )


def test_collect_rapid_swap_candidates_finds_duplicate_swap_tx_ids_in_same_block():
    recorder = RapidSwapRecorder(DepContainer())
    block = make_block(
        make_swap_event('rapid-1', 123, pool='BSC.USDT-0xabc', stream_count=60, stream_quantity=222),
        make_swap_event('rapid-1', 123, pool='BASE.ETH', stream_count=61, stream_quantity=222),
        make_swap_event('normal-1', 123, pool='ETH.ETH'),
        make_outbound_event('rapid-1', 123),
    )

    candidates = recorder.collect_rapid_swap_candidates(block)

    assert list(candidates.keys()) == ['rapid-1']
    assert len(candidates['rapid-1']) == 2


def test_collect_rapid_swap_candidates_ignores_multi_hop_same_streaming_count():
    recorder = RapidSwapRecorder(DepContainer())
    block = make_block(
        make_swap_event('not-rapid', 123, pool='ETH.ETH', stream_count=60, stream_quantity=222),
        make_swap_event('not-rapid', 123, pool='BTC.BTC', coin='100000000 THOR.RUNE', stream_count=60, stream_quantity=222),
        make_outbound_event('not-rapid', 123),
    )

    candidates = recorder.collect_rapid_swap_candidates(block)

    assert candidates == {}


@pytest.mark.asyncio
async def test_on_data_accepts_block_result_stores_last_candidates_and_persists_daily_stats():
    recorder = RapidSwapRecorder(make_deps())
    block = make_block(
        make_swap_event('rapid-2', 555, pool='BTC.BTC', coin='100000000 BTC.BTC', from_addr='thor1rapid', stream_count=60, stream_quantity=222),
        make_swap_event('rapid-2', 555, pool='ETH.ETH', coin='100000000 BTC.BTC', from_addr='thor1rapid', stream_count=61, stream_quantity=222),
        make_swap_event('normal-1', 555, pool='ETH.ETH', coin='100000000 THOR.RUNE', from_addr='thor1normal'),
        block_no=555,
    )

    await recorder.on_data(None, block)
    await recorder.on_data(None, block)

    day_stats = await recorder.accumulator.get(block.timestamp)

    assert recorder.last_seen_block_no == 555
    assert 'rapid-2' in recorder.last_rapid_candidates
    assert len(recorder.last_rapid_candidates['rapid-2']) == 2
    assert day_stats['rapid_swap_count'] == 1.0
    assert day_stats['total_swap_count'] == 2.0
    assert day_stats['unique_users'] == 1.0
    assert day_stats['rapid_swap_volume_usd'] == 60_000.0
    assert day_stats['rapid_swap_blocks_saved'] == 1.0
    assert day_stats['rapid_swap_event_count'] == 2.0


@pytest.mark.asyncio
async def test_get_daily_data_and_summary_use_true_cross_day_uniques():
    recorder = RapidSwapRecorder(make_deps())

    day1 = 1_700_000_000
    day2 = day1 + 86_400

    await recorder.on_data(None, make_block(
        make_swap_event('rapid-day-1', 600, pool='BTC.BTC', coin='100000000 BTC.BTC', from_addr='thor1same', stream_count=60, stream_quantity=222),
        make_swap_event('rapid-day-1', 600, pool='ETH.ETH', coin='100000000 BTC.BTC', from_addr='thor1same', stream_count=61, stream_quantity=222),
        make_swap_event('normal-day-1', 600, pool='ETH.ETH', coin='100000000 THOR.RUNE', from_addr='thor1other'),
        block_no=600,
        timestamp=day1,
    ))

    await recorder.on_data(None, make_block(
        make_swap_event('rapid-day-2', 601, pool='BTC.BTC', coin='100000000 BTC.BTC', from_addr='thor1same', stream_count=60, stream_quantity=222),
        make_swap_event('rapid-day-2', 601, pool='ETH.ETH', coin='100000000 BTC.BTC', from_addr='thor1same', stream_count=61, stream_quantity=222),
        make_swap_event('normal-day-2', 601, pool='ETH.ETH', coin='100000000 THOR.RUNE', from_addr='thor1another'),
        block_no=601,
        timestamp=day2,
    ))

    daily = await recorder.get_daily_data(days=2, end_ts=day2)
    assert len(daily) == 2
    assert daily[0]['rapid_swap_count'] == 1.0
    assert daily[0]['total_swap_count'] == 2.0
    assert daily[0]['unique_users'] == 1.0
    assert daily[0]['rapid_swap_share'] == 0.5
    assert daily[1]['rapid_swap_count'] == 1.0
    assert daily[1]['total_swap_count'] == 2.0
    assert daily[1]['unique_users'] == 1.0
    assert daily[1]['rapid_swap_volume_usd'] == 60_000.0
    assert daily[1]['rapid_swap_blocks_saved'] == 1.0

    summary = await recorder.get_summary(days=2, end_ts=day2)
    assert summary['rapid_swap_count'] == 2.0
    assert summary['total_swap_count'] == 4.0
    assert summary['unique_users'] == 1.0
    assert summary['rapid_swap_volume_usd'] == 120_000.0
    assert summary['rapid_swap_blocks_saved'] == 2.0
    assert summary['rapid_swap_event_count'] == 4.0
    assert summary['rapid_swap_share'] == 0.5


@pytest.mark.asyncio
async def test_on_data_initializes_hll_counters_when_db_redis_is_not_ready_yet():
    deps = make_lazy_db_deps()
    recorder = RapidSwapRecorder(deps)

    assert deps.db.redis is None

    await recorder.on_data(None, make_block(
        make_swap_event('rapid-lazy', 777, pool='BTC.BTC', coin='100000000 BTC.BTC', from_addr='thor1lazy', stream_count=60, stream_quantity=222),
        make_swap_event('rapid-lazy', 777, pool='ETH.ETH', coin='100000000 BTC.BTC', from_addr='thor1lazy', stream_count=61, stream_quantity=222),
        make_swap_event('normal-lazy', 777, pool='ETH.ETH', coin='100000000 THOR.RUNE', from_addr='thor1normal'),
        block_no=777,
    ))

    assert deps.db.redis is not None

    day_stats = await recorder.accumulator.get(1_700_000_000)
    assert day_stats['rapid_swap_count'] == 1.0
    assert day_stats['total_swap_count'] == 2.0
    assert day_stats['unique_users'] == 1.0


