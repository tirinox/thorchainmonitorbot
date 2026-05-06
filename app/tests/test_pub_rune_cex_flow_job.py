from types import SimpleNamespace

import pytest

from models.transfer import AlertRuneTransferStats
from notify.pub_configure import PublicAlertJobExecutor
from tools.dashboard.components.cex_flow import rune_transfer_stats_dashboard_info_async


@pytest.mark.asyncio
async def test_job_rune_transfer_stats_uses_rune_transfer_recorder(monkeypatch):
    captured = {}

    class FakeRecorder:
        def __init__(self, deps):
            self.deps = deps

        async def get_summary(self, days):
            captured['days'] = days
            return {
                'days': days,
                'start_date': '2026-04-08',
                'end_date': '2026-04-14',
                'volume_rune': 17_500.0,
                'transfer_count': 3,
                'cex_inflow_rune': 15_000.0,
                'cex_outflow_rune': 2_500.0,
                'cex_inflow_count': 2,
                'cex_outflow_count': 1,
                'cex_netflow_rune': 12_500.0,
                'daily': [],
            }

    async def fake_handle_data(data):
        captured['data'] = data

    monkeypatch.setattr('notify.pub_configure.RuneTransferRecorder', FakeRecorder)

    executor = PublicAlertJobExecutor.__new__(PublicAlertJobExecutor)
    executor.deps = SimpleNamespace(
        alert_presenter=SimpleNamespace(handle_data=fake_handle_data),
        pool_cache=SimpleNamespace(get_usd_per_rune=lambda: None),
    )

    async def fake_get_usd_per_rune():
        return 2.75

    executor.deps.pool_cache.get_usd_per_rune = fake_get_usd_per_rune

    await executor.job_rune_transfer_stats()

    assert captured['days'] == PublicAlertJobExecutor.RUNE_TRANSFER_STATS_SUMMARY_DAYS
    assert isinstance(captured['data'], AlertRuneTransferStats)
    assert captured['data'].period_days == PublicAlertJobExecutor.RUNE_TRANSFER_STATS_SUMMARY_DAYS
    assert captured['data'].transfer_count == 3
    assert captured['data'].usd_per_rune == 2.75


@pytest.mark.asyncio
async def test_job_rune_transfer_stats_allows_days_override(monkeypatch):
    captured = {}

    class FakeRecorder:
        def __init__(self, deps):
            self.deps = deps

        async def get_summary(self, days):
            captured['days'] = days
            return {
                'days': days,
                'start_date': '2026-04-08',
                'end_date': '2026-04-10',
                'volume_rune': 9_999.0,
                'transfer_count': 2,
                'cex_inflow_rune': 8_000.0,
                'cex_outflow_rune': 1_999.0,
                'cex_inflow_count': 1,
                'cex_outflow_count': 1,
                'cex_netflow_rune': 6_001.0,
                'daily': [],
            }

    async def fake_handle_data(data):
        captured['data'] = data

    async def fake_get_usd_per_rune():
        return 3.25

    monkeypatch.setattr('notify.pub_configure.RuneTransferRecorder', FakeRecorder)

    executor = PublicAlertJobExecutor.__new__(PublicAlertJobExecutor)
    executor.deps = SimpleNamespace(
        alert_presenter=SimpleNamespace(handle_data=fake_handle_data),
        pool_cache=SimpleNamespace(get_usd_per_rune=fake_get_usd_per_rune),
    )

    await executor.job_rune_transfer_stats(days=3, ignored_flag=True)

    assert captured['days'] == 3
    assert isinstance(captured['data'], AlertRuneTransferStats)
    assert captured['data'].period_days == 3
    assert captured['data'].usd_per_rune == 3.25


@pytest.mark.asyncio
async def test_rune_transfer_stats_dashboard_info_async_uses_summary(monkeypatch):
    captured = {}

    class FakeRecorder:
        def __init__(self, deps):
            self.deps = deps

        async def get_summary(self, days):
            captured['days'] = days
            return {
                'days': days,
                'start_date': '2026-04-08',
                'end_date': '2026-04-14',
                'volume_rune': 12_579.0,
                'transfer_count': 4,
                'cex_inflow_rune': 12_345.0,
                'cex_outflow_rune': 234.0,
                'cex_inflow_count': 3,
                'cex_outflow_count': 1,
                'cex_netflow_rune': 12_111.0,
                'daily': [],
            }

    async def fake_get_usd_per_rune():
        return 3.5

    monkeypatch.setattr('tools.dashboard.components.cex_flow.RuneTransferRecorder', FakeRecorder)

    app = SimpleNamespace(
        deps=SimpleNamespace(
            pool_cache=SimpleNamespace(get_usd_per_rune=fake_get_usd_per_rune),
        )
    )

    data = await rune_transfer_stats_dashboard_info_async(app)

    assert captured['days'] == PublicAlertJobExecutor.RUNE_TRANSFER_STATS_SUMMARY_DAYS
    assert isinstance(data, AlertRuneTransferStats)
    assert data.period_days == PublicAlertJobExecutor.RUNE_TRANSFER_STATS_SUMMARY_DAYS
    assert data.cex_inflow_rune == 12_345.0
    assert data.usd_per_rune == 3.5
