from types import SimpleNamespace

import pytest

import jobs.fetch.net_stats as net_stats_mod
from jobs.achievement.ach_list import A
from jobs.achievement.extractor import AchievementsExtractor
from jobs.fetch.net_stats import NetworkStatisticsFetcher
from models.net_stats import NetworkStats
from models.swap_history import SwapHistoryResponse


def _day(usd, count=10):
    # Midgard gives USD in cents
    return {'totalVolumeUSD': str(int(usd * 100)), 'totalCount': str(count), 'totalVolume': '0'}


def _history(days_usd, running_day=True, meta_usd=0):
    intervals = [_day(v) for v in days_usd]
    if running_day:
        intervals.append(_day(0, count=0))  # Midgard reports the running interval as empty
    return SwapHistoryResponse.from_json({'intervals': intervals, 'meta': _day(meta_usd)})


def test_last_whole_intervals_skip_the_running_day():
    h = _history([1, 2, 3, 4])
    assert [d.total_volume_usd for d in h.last_whole_intervals(3)] == [2, 3, 4]
    h = _history([1, 2, 3, 4], running_day=False)
    assert [d.total_volume_usd for d in h.last_whole_intervals(3)] == [2, 3, 4]


class _Midgard:
    def __init__(self, days, years_meta):
        self.days, self.years_meta = days, years_meta
        self.year_calls = 0

    async def query_swap_stats(self, count=10, interval='day', **_):
        if interval == 'year':
            self.year_calls += 1
            return _history([], running_day=False, meta_usd=self.years_meta)
        return _history(self.days[-(count - 1):])


@pytest.fixture
def fetcher(monkeypatch):
    monkeypatch.setattr(NetworkStatisticsFetcher, '_total_volume_usd_cache', (0.0, 0.0))
    monkeypatch.setattr(net_stats_mod, 'now_ts', lambda: 1_000_000.0)
    midgard = _Midgard(days=[1_000_000.0 * (i + 1) for i in range(40)], years_meta=123_000_000_000)
    cfg = SimpleNamespace(net_summary=SimpleNamespace(fetch_period='125s'), sleep_step=0)
    deps = SimpleNamespace(cfg=cfg, midgard_connector=midgard, data_controller=None)
    return NetworkStatisticsFetcher(deps, 0), midgard


@pytest.mark.asyncio
async def test_swap_volumes_in_usd(fetcher):
    f, midgard = fetcher
    ns = NetworkStats()
    await f._get_swap_stats(ns)

    assert ns.swap_volume_day_usd == 40_000_000  # the last whole day
    assert ns.swap_volume_30d_usd == sum(1_000_000 * d for d in range(11, 41))  # the last 30 whole days
    assert ns.swap_volume_total_usd == 123_000_000_000

    # the all-time volume is asked once in a while, and by all fetchers together
    await NetworkStatisticsFetcher(f.deps, 0)._get_swap_stats(NetworkStats())
    assert midgard.year_calls == 1


@pytest.mark.asyncio
async def test_no_monthly_volume_without_30_whole_days(fetcher):
    f, midgard = fetcher
    midgard.days = midgard.days[:10]
    ns = NetworkStats()
    await f._get_swap_stats(ns)
    assert ns.swap_volume_30d_usd == 0  # a partial month would be taken for a record low


def test_network_stats_feed_usd_swap_volumes():
    ns = NetworkStats(swap_volume_day_usd=38e6, swap_volume_30d_usd=2.41e9, swap_volume_total_usd=123.3e9)
    values = {a.key: a.value for a in AchievementsExtractor.on_network_stats(ns)}
    assert values[A.DAILY_VOLUME] == 38_000_000
    assert values[A.MONTHLY_SWAP_VOLUME] == 2_410_000_000
    assert values[A.SWAP_VOLUME_TOTAL_USD] == 123_300_000_000
    assert 'swap_volume_total_rune' not in values
