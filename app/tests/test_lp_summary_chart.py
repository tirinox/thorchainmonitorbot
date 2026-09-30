from types import SimpleNamespace
from unittest.mock import create_autospec

import pytest

from jobs.runeyield.date2block import DateToBlockMapper
from jobs.runeyield.lp_my import HomebrewLPConnector
from models.memo import ActionType
from models.pool_info import PoolInfo

POOL = 'ETH.ETH'
LAST_BLOCK = 5_000_000
MY_UNITS = 1_000


class FakeTx:
    def __init__(self, ts, units):
        self.first_pool = POOL
        self.date_timestamp = ts
        self.meta_add = SimpleNamespace(liquidity_units_int=units)
        self.meta_withdraw = None

    def is_of_type(self, action):
        return action == ActionType.ADD_LIQUIDITY


class FakePoolCache:
    stable_coins = []

    def __init__(self):
        self.heights = []

    async def load_pools_at(self, height, ts, pools):
        self.heights.append(height)
        # 1% of the pool is mine: 100 RUNE of 10_000; an ETH costs $2000 and 100 RUNE, so a RUNE is $20
        return {POOL: PoolInfo(POOL, balance_asset=100 * 10 ** 8, balance_rune=10_000 * 10 ** 8,
                               pool_units=100_000, status='available', units=100 * MY_UNITS, usd_per_asset=2000.0)}


def _make_connector():
    # skip __init__: it needs the config and HTTP connectors
    conn = HomebrewLPConnector.__new__(HomebrewLPConnector)
    # autospec: calling a method DateToBlockMapper does not have fails, as the removed one did in production
    conn.block_mapper = create_autospec(DateToBlockMapper, instance=True)
    conn.block_mapper.get_block_height_by_timestamp.side_effect = lambda ts, last_block=None: LAST_BLOCK - 10

    async def get_thor_block():
        return LAST_BLOCK

    conn.deps = SimpleNamespace(
        last_block_cache=SimpleNamespace(get_thor_block=get_thor_block),
        pool_cache=FakePoolCache(),
    )
    return conn


@pytest.mark.asyncio
async def test_chart_prices_each_day_at_its_own_block():
    conn = _make_connector()
    txs = [FakeTx(ts=1_000_000, units=MY_UNITS)]  # long before the chart window

    charts = await conn._get_charts(txs, days=3)

    points = charts[POOL]
    assert len(points) == 3
    assert [p.timestamp for p in points] == sorted(p.timestamp for p in points)  # chronological
    # my 100 RUNE + 1 ETH = 200 RUNE at $20
    assert all(p.usd_value == pytest.approx(4000.0) for p in points)

    calls = conn.block_mapper.get_block_height_by_timestamp.call_args_list
    assert [c.args[0] for c in calls] == [p.timestamp for p in reversed(points)]
    assert all(c.kwargs['last_block'] == LAST_BLOCK for c in calls)


@pytest.mark.asyncio
async def test_chart_never_asks_for_a_block_past_the_tip():
    conn = _make_connector()
    conn.block_mapper.get_block_height_by_timestamp.side_effect = lambda ts, last_block=None: LAST_BLOCK + 1800

    await conn._get_charts([FakeTx(ts=1_000_000, units=MY_UNITS)], days=2)

    assert conn.deps.pool_cache.heights == [LAST_BLOCK, LAST_BLOCK]
