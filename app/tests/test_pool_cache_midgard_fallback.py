from types import SimpleNamespace

import pytest

from api.midgard.urlgen import free_url_gen
from jobs.fetch.cached.pool import PoolCache
from jobs.runeyield.lp_my import HomebrewLPConnector
from models.pool_info import PoolInfoHistoricEntry
from tests.fakes import FakeDB

USDC = 'ETH.USDC-0XA0B86991C6218B36C1D19D4A2E9EB0CE3606EB48'
TCY = 'THOR.TCY'
TS = 1756404547

# Midgard's 5-min interval that contains THOR.TCY add liquidity at block 22598558
TCY_DEPTH = PoolInfoHistoricEntry.from_json({
    'assetDepth': '251433376159537',
    'assetPrice': '0.15101894380798073',
    'assetPriceUSD': '0.18840988598451347',
    'endTime': '1756404600',
    'liquidityUnits': '30707726659724',
    'runeDepth': '37971202905688',
    'synthSupply': '0',
    'synthUnits': '0',
    'units': '30707726659724',
})

# the pool did not exist yet
EMPTY_DEPTH = PoolInfoHistoricEntry.from_json({
    'assetDepth': '0', 'assetPrice': '0', 'assetPriceUSD': 'NaN', 'runeDepth': '0', 'units': '0',
})


class FakeThorConnector:
    def __init__(self):
        self.heights = []

    async def query_pools(self, height=None):
        self.heights.append(height)
        return None  # pruned state


class FakeMidgard:
    def __init__(self, depths):
        self.depths = depths
        self.calls = []

    async def query_pool_depth_at(self, pool, ts):
        self.calls.append((pool, ts))
        return self.depths.get(pool)


def make_deps(midgard):
    return SimpleNamespace(
        cfg=SimpleNamespace(stable_coins=[USDC], price=SimpleNamespace(pool_cache_max_age='30d')),
        db=FakeDB(),
        thor_connector=FakeThorConnector(),
        thor_connector_archive=FakeThorConnector(),
        midgard_connector=midgard,
    )


def test_url_pool_depth_at_asks_for_one_5min_interval():
    assert free_url_gen.url_pool_depth_at(TCY, 1756404547.9) == \
           '/v2/history/depths/THOR.TCY?interval=5min&from=1756404547&to=1756404548'


def test_historic_entry_to_pool_info_keeps_total_units_and_usd_price():
    entry = PoolInfoHistoricEntry.from_json({
        'assetDepth': '100', 'runeDepth': '200', 'liquidityUnits': '70', 'synthUnits': '30', 'units': '100',
        'assetPriceUSD': '4.0',
    })
    pool = entry.to_pool_info('BTC.BTC')
    assert pool.pool_units == 70
    assert pool.units == 100
    assert pool.usd_per_asset == 4.0


@pytest.mark.asyncio
async def test_load_pools_at_rebuilds_pruned_height_from_midgard():
    midgard = FakeMidgard({TCY: TCY_DEPTH, 'BTC.BTC': EMPTY_DEPTH})
    deps = make_deps(midgard)
    cache = PoolCache(deps)

    pool_map = await cache.load_pools_at(22598558, TS, {TCY, 'BTC.BTC'})

    assert deps.thor_connector.heights == [22598558]
    assert deps.thor_connector_archive.heights == [22598558]
    assert sorted(midgard.calls) == [('BTC.BTC', TS), (TCY, TS)]

    # only the pool that existed at that moment
    assert list(pool_map) == [TCY]
    tcy = pool_map[TCY]
    assert tcy.balance_asset == 251433376159537
    assert tcy.balance_rune == 37971202905688
    assert tcy.units == 30707726659724
    assert tcy.usd_per_rune == pytest.approx(1.2476, abs=1e-4)

    # partial maps from Midgard must not land in the height cache
    assert await cache._load_history_data(22598558) is None


@pytest.mark.asyncio
async def test_load_pools_at_raises_if_midgard_has_nothing_either():
    cache = PoolCache(make_deps(FakeMidgard({})))
    with pytest.raises(RuntimeError):
        await cache.load_pools_at(22598558, TS, {TCY})


def test_rune_price_falls_back_to_pool_usd_price_without_stable_coins():
    lp = HomebrewLPConnector.__new__(HomebrewLPConnector)
    lp.deps = SimpleNamespace(pool_cache=SimpleNamespace(stable_coins=[USDC]))

    price = lp._calculate_weighted_rune_price_in_usd({TCY: TCY_DEPTH.to_pool_info(TCY)})
    assert price == pytest.approx(1.2476, abs=1e-4)

    with pytest.raises(ValueError):
        lp._calculate_weighted_rune_price_in_usd({})
