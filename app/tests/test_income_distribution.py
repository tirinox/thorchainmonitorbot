import logging
from types import SimpleNamespace

import pytest

from jobs.fetch.key_stats import KeyStatsFetcher
from lib.date_utils import HOUR, DAY
from models.affiliate import AffiliateHistoryResponse
from models.earnings_history import EarningsInterval, PoolEarnings, EarningHistoryResponse, IncomeCategory, \
    build_income_distribution

E8 = 10 ** 8
START_TS = 1_790_172_000  # a whole hour
WEEK = 7 * DAY


def _pool(name, earnings, rewards=None, fees=0):
    return PoolEarnings(
        asset_liquidity_fees=0, earnings=earnings, pool=name,
        rewards=earnings - fees if rewards is None else rewards,
        rune_liquidity_fees=0, saver_earning=0, total_liquidity_fees_rune=fees,
    )


def _interval(start_ts, *, income=1000 * E8, price=2.0, bond_bps=5000, dev_bps=500, marketing_bps=500,
              burn_bps=100, tcy_bps=1000, pol_bps=2000, extra_pools=(), length=HOUR):
    """One Midgard earnings interval that distributes `income` by the given shares; pools get the rest"""

    def part(bps):
        return income * bps // 10_000

    bond = part(bond_bps)
    special = [
        _pool('dev_fund_reward', part(dev_bps)),
        _pool('marketing_fund_reward', part(marketing_bps)),
        _pool('income_burn', part(burn_bps)),
        _pool('tcy_stake_reward', part(tcy_bps)),
        _pool('pol_reserve_reward', part(pol_bps)),
    ]
    pools_total = income - bond - sum(p.earnings for p in special) - sum(p.earnings for p in extra_pools)
    # as in real data: the pools earned the fees, and then most of them were taken away as a negative reward
    btc = _pool('BTC.BTC', pools_total * 3 // 4, fees=income * 3 // 4)
    eth = _pool('ETH.ETH', pools_total - btc.earnings, fees=income - income * 3 // 4)
    pools = [btc, eth, *special, *extra_pools]
    return EarningsInterval(
        avg_node_count=100.0,
        block_rewards=0,
        bonding_earnings=bond,
        earnings=income,
        end_time=start_ts + length,
        liquidity_earnings=income - bond,
        liquidity_fees=income,
        pools=pools,
        rune_price_usd=price,
        start_time=start_ts,
    )


def _hours(n, start_ts=START_TS, **kwargs):
    return [_interval(start_ts + i * HOUR, **kwargs) for i in range(n)]


def _amounts(distribution):
    return {c.key: c.rune_raw for c in distribution.categories}


def test_categories_add_up_without_double_counting_special_rows():
    intervals = _hours(3)
    d = build_income_distribution(intervals, START_TS, START_TS + 3 * HOUR)

    assert d.is_complete
    assert [c.key for c in d.categories] == list(IncomeCategory.ORDER)
    assert _amounts(d) == {
        'nodes': 1500 * E8, 'pools': 270 * E8, 'pol_reserve': 600 * E8, 'tcy': 300 * E8,
        'dev_fund': 150 * E8, 'marketing': 150 * E8, 'burn': 30 * E8,
    }
    assert d.total_rune_raw == 3000 * E8
    assert d.discrepancy_rune_raw == 0
    assert sum(_amounts(d).values()) == d.total_rune_raw

    # liquidityEarnings contains the special rows, so it is much more than the pools really got
    assert sum(i.liquidity_earnings for i in intervals) == 1500 * E8

    assert d.total_usd == pytest.approx(6000.0)
    assert d.find('pools').usd == pytest.approx(540.0)
    assert d.find('pools').share == pytest.approx(0.09)
    assert sum(c.share for c in d.categories) == pytest.approx(1.0)


def test_pool_income_is_final_earnings_not_rewards():
    interval = _interval(START_TS)
    real_pools = [p for p in interval.pools if '.' in p.pool]
    assert all(p.rewards < 0 for p in real_pools)

    d = build_income_distribution([interval], START_TS, START_TS + HOUR)
    assert d.find('pools').rune_raw == sum(p.earnings for p in real_pools) == 90 * E8


def test_parameter_change_inside_the_period_uses_actual_accruals():
    # the burn share went from 1% to 5% and the POL share from 20% to 0 in the middle of the period
    before = _hours(2)
    after = _hours(2, start_ts=START_TS + 2 * HOUR, burn_bps=500, pol_bps=0)
    d = build_income_distribution(before + after, START_TS, START_TS + 4 * HOUR)

    assert d.is_complete
    amounts = _amounts(d)
    assert amounts['burn'] == (10 + 10 + 50 + 50) * E8
    assert amounts['pol_reserve'] == 400 * E8
    # neither the old nor the new rate applied to the whole period gives these amounts
    assert amounts['burn'] not in (4000 * E8 * 100 // 10_000, 4000 * E8 * 500 // 10_000)
    assert d.discrepancy_rune_raw == 0


def test_usd_uses_the_price_of_each_interval():
    intervals = [_interval(START_TS, price=1.0), _interval(START_TS + HOUR, price=3.0)]
    d = build_income_distribution(intervals, START_TS, START_TS + 2 * HOUR)
    assert d.total_rune == 2000
    assert d.total_usd == pytest.approx(1000 * 1.0 + 1000 * 3.0)
    assert d.find('nodes').usd == pytest.approx(500 * 1.0 + 500 * 3.0)


def test_unknown_special_row_is_kept_as_other():
    interval = _interval(START_TS, extra_pools=[_pool('stable_reserve_reward', 40 * E8)])
    d = build_income_distribution([interval], START_TS, START_TS + HOUR)

    assert d.categories[-1].key == IncomeCategory.OTHER
    assert d.find('other').rune_raw == 40 * E8
    assert d.find('pools').rune_raw == 50 * E8
    assert d.discrepancy_rune_raw == 0


def test_discrepancy_is_reported_not_normalised():
    interval = _interval(START_TS)._replace(earnings=1001 * E8)
    d = build_income_distribution([interval], START_TS, START_TS + HOUR)
    assert d.discrepancy_rune_raw == 1 * E8
    assert sum(_amounts(d).values()) == 1000 * E8


@pytest.mark.parametrize('intervals, issue', [
    ([], 'no intervals'),
    (_hours(3)[:2], 'intervals end at'),
    (_hours(3)[1:], 'gap or overlap'),
    ([*_hours(1), *_hours(1, start_ts=START_TS + 2 * HOUR)], 'gap or overlap'),
    ([_interval(START_TS, length=3 * HOUR)], 'is not 3600 sec long'),
    ([*_hours(2), _interval(START_TS + 2 * HOUR, income=0)], '1 empty interval(s)'),
])
def test_incomplete_coverage_is_flagged(intervals, issue):
    d = build_income_distribution(intervals, START_TS, START_TS + 3 * HOUR)
    assert not d.is_complete
    assert any(issue in i for i in d.issues), d.issues


def test_calc_earnings_converts_every_field_to_usd():
    e = EarningHistoryResponse.calc_earnings(_hours(2, price=2.0))
    assert e.total_earnings == pytest.approx(4000.0)
    assert e.bonding_earnings == pytest.approx(2000.0)
    assert e.liquidity_earnings == pytest.approx(2000.0)


# ---- Fetcher ----

class _FakeMidgard:
    def __init__(self, last_aggregated_ts, earnings_by_start, affiliates_by_start=None):
        self.last_aggregated_ts = last_aggregated_ts
        self.earnings_by_start = earnings_by_start
        self.affiliates_by_start = affiliates_by_start or {}
        self.earnings_calls = []

    async def query_earnings(self, from_ts=0, to_ts=0, count=0, interval=''):
        self.earnings_calls.append((from_ts, to_ts, interval))
        intervals = self.earnings_by_start[from_ts]
        return SimpleNamespace(intervals=intervals)

    async def query_last_aggregated_ts(self):
        return self.last_aggregated_ts

    async def query_affiliates(self, count=14, interval='day', from_ts=0, to_ts=0):
        assert not interval
        volume_usd = self.affiliates_by_start[from_ts]
        row = {
            'startTime': from_ts, 'endTime': to_ts, 'count': '1', 'volume': '1', 'volumeUSD': str(volume_usd),
            'thornames': [{'thorname': 't', 'count': '1', 'volume': '1', 'volumeUSD': str(volume_usd)}],
        }
        return AffiliateHistoryResponse(meta=row, intervals=[row])


class _FakeThor:
    def __init__(self, block_time):
        self.block_time = block_time

    async def query_thorchain_block_raw(self, height):
        assert height is None
        return {'header': {'time': self.block_time}}


def _make_fetcher(midgard=None, block_time='2026-09-30T13:49:56.785323732Z') -> KeyStatsFetcher:
    fetcher = KeyStatsFetcher.__new__(KeyStatsFetcher)
    fetcher.tally_days_period = 7
    fetcher.logger = logging.getLogger('test')
    aff_man = SimpleNamespace(get_affiliate_logo=lambda name, with_local_prefix: '')
    fetcher.deps = SimpleNamespace(
        thor_connector=_FakeThor(block_time),
        midgard_connector=midgard,
        name_service=SimpleNamespace(get_affiliate_name=lambda name: name, aff_man=aff_man),
    )
    return fetcher


@pytest.mark.asyncio
async def test_tally_period_ends_at_the_last_full_hour_of_the_last_block():
    start_ts, end_ts = await _make_fetcher().get_tally_period()
    assert end_ts == 1_790_773_200  # 2026-09-30 13:00:00 UTC
    assert end_ts - start_ts == WEEK


@pytest.mark.asyncio
async def test_tally_period_fails_without_block_time():
    with pytest.raises(ConnectionError):
        await _make_fetcher(block_time=None).get_tally_period()


@pytest.mark.asyncio
async def test_current_week_is_the_latest_one():
    end_ts = START_TS + WEEK
    midgard = _FakeMidgard(end_ts + 60, {
        START_TS: _hours(168, income=1000 * E8),
        START_TS - WEEK: _hours(168, start_ts=START_TS - WEEK, income=100 * E8),
    })
    curr, prev, income = await _make_fetcher(midgard).get_earnings_curr_prev(START_TS, end_ts)

    assert sorted(midgard.earnings_calls) == [(START_TS - WEEK, START_TS, 'hour'), (START_TS, end_ts, 'hour')]
    assert curr.total_earnings == pytest.approx(168 * 1000 * 2.0)
    assert prev.total_earnings == pytest.approx(168 * 100 * 2.0)
    assert income.is_complete
    assert income.total_usd == pytest.approx(curr.total_earnings)
    assert income.prev_total_usd == pytest.approx(prev.total_earnings)


@pytest.mark.asyncio
async def test_lagging_midgard_makes_the_data_incomplete():
    end_ts = START_TS + WEEK
    midgard = _FakeMidgard(end_ts - 10 * 60, {
        START_TS: _hours(168),
        START_TS - WEEK: _hours(168, start_ts=START_TS - WEEK),
    })
    _, _, income = await _make_fetcher(midgard).get_earnings_curr_prev(START_TS, end_ts)
    assert not income.is_complete
    assert 'Midgard is behind' in income.issues[0]


@pytest.mark.asyncio
async def test_previous_week_with_gaps_gives_no_delta():
    end_ts = START_TS + WEEK
    midgard = _FakeMidgard(end_ts, {
        START_TS: _hours(168),
        START_TS - WEEK: _hours(100, start_ts=START_TS - WEEK),
    })
    _, _, income = await _make_fetcher(midgard).get_earnings_curr_prev(START_TS, end_ts)
    assert income.is_complete
    assert income.prev_total_usd is None


@pytest.mark.asyncio
async def test_affiliates_of_the_current_and_previous_week_are_not_swapped():
    midgard = _FakeMidgard(0, {}, affiliates_by_start={START_TS: 700, START_TS - WEEK: 300})
    top, curr_usd, prev_usd = await _make_fetcher(midgard).get_top_affiliates(START_TS, START_TS + WEEK)
    assert (curr_usd, prev_usd) == (700, 300)
    assert (top[0].total_usd, top[0].prev_total_usd) == (700, 300)
