from types import SimpleNamespace

import pytest

from jobs.fetch.top_pools import BestPoolsFetcher
from lib.prev_state import PrevStateDB
from models.pool_info import PoolInfo, PoolMapStruct, EventPools
from tests.fakes import FakeDB

USDC = 'ETH.USDC-0XA0B86991C6218B36C1D19D4A2E9EB0CE3606EB48'


def make_pool_map(scale=1):
    return {
        'BTC.BTC': PoolInfo(
            'BTC.BTC',
            balance_asset=100_000_000 * scale,
            balance_rune=1_500_000_000_000 * scale,
            pool_units=1,
            status=PoolInfo.AVAILABLE,
            usd_per_asset=30_000.0,
            volume_24h=10_000_000_000 * scale,
        ),
        USDC: PoolInfo(
            USDC,
            balance_asset=2_000_000_000_000 * scale,
            balance_rune=1_000_000_000_000 * scale,
            pool_units=1,
            status=PoolInfo.AVAILABLE,
            usd_per_asset=1.0,
            volume_24h=5_000_000_000 * scale,
        ),
    }


def make_fetcher(monkeypatch, db, pool_map):
    class FakeMidgardPoolFetcher:
        def __init__(self, deps, period):
            pass

        async def fetch_as_pool_map_struct(self):
            return PoolMapStruct(pool_map, 1_000)

    async def fake_query_earnings(count, interval):
        return None

    monkeypatch.setattr('jobs.fetch.top_pools.PoolInfoFetcherMidgard', FakeMidgardPoolFetcher)
    deps = SimpleNamespace(
        db=db,
        cfg=SimpleNamespace(stable_coins=[USDC]),
        midgard_connector=SimpleNamespace(query_earnings=fake_query_earnings),
    )
    return BestPoolsFetcher(deps)


@pytest.mark.asyncio
async def test_pool_map_struct_survives_prev_state_round_trip():
    pvdb = PrevStateDB(FakeDB(), PoolMapStruct)
    original = PoolMapStruct(make_pool_map(), 1_000)

    await pvdb.set(original)
    loaded = await pvdb.get()

    assert loaded.timestamp == 1_000
    assert loaded.pool_map == original.pool_map


@pytest.mark.asyncio
async def test_top_pools_without_prev_state_does_not_fail(monkeypatch):
    fetcher = make_fetcher(monkeypatch, FakeDB(), make_pool_map())

    event_pools, pool_map_struct = await fetcher.get_top_pools()

    assert event_pools.pool_detail_dic_prev == {}
    assert event_pools.get_difference_percent('BTC.BTC', EventPools.BY_DEPTH) is None
    assert event_pools.total_liquidity_diff_percent is None

    # the job saves this, so the next run has a previous state
    await fetcher.save_prev_pool_map(pool_map_struct)
    event_pools, _ = await fetcher.get_top_pools()
    assert event_pools.get_difference_percent('BTC.BTC', EventPools.BY_DEPTH) == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_top_pools_changes_against_prev_state(monkeypatch):
    db = FakeDB()
    await PrevStateDB(db, PoolMapStruct).set(PoolMapStruct(make_pool_map(scale=1), 1_000))
    fetcher = make_fetcher(monkeypatch, db, make_pool_map(scale=2))

    event_pools, _ = await fetcher.get_top_pools()

    assert event_pools.get_difference_percent('BTC.BTC', EventPools.BY_DEPTH) == pytest.approx(100.0)
    assert event_pools.get_difference_percent('BTC.BTC', EventPools.BY_VOLUME_24h) == pytest.approx(100.0)


def test_difference_percent_for_pool_missing_in_prev_state():
    prev = make_pool_map()
    del prev['BTC.BTC']
    event_pools = EventPools(make_pool_map(), prev, usd_per_rune=2.0)

    assert event_pools.get_difference_percent('BTC.BTC', EventPools.BY_DEPTH) is None
    assert event_pools.get_difference_percent(USDC, EventPools.BY_DEPTH) == pytest.approx(0.0)
