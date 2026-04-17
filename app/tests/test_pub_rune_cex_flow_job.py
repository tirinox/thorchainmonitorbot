from types import SimpleNamespace

import pytest

from lib.date_utils import DAY
from models.transfer import RuneCEXFlow
from notify.pub_configure import PublicAlertJobExecutor
from jobs.transfer_recorder import RuneTransferRecorder


@pytest.mark.asyncio
async def test_job_rune_cex_flow_uses_rune_transfer_recorder(monkeypatch):
    captured = {}

    class FakeRecorder:
        def __init__(self, deps):
            self.deps = deps
            self.min_rune_in_summary = 10_000

        async def get_cex_flow(self, period):
            captured['period'] = period
            return RuneCEXFlow(
                rune_cex_inflow=15_000.0,
                rune_cex_outflow=2_500.0,
                total_transfers=3,
                usd_per_rune=2.75,
                period_sec=period,
            )

    async def fake_handle_data(data):
        captured['data'] = data

    monkeypatch.setattr('notify.pub_configure.RuneTransferRecorder', FakeRecorder)

    executor = PublicAlertJobExecutor.__new__(PublicAlertJobExecutor)
    executor.deps = SimpleNamespace(
        alert_presenter=SimpleNamespace(handle_data=fake_handle_data),
        emergency=SimpleNamespace(report=lambda *args, **kwargs: captured.setdefault('emergency_calls', []).append((args, kwargs))),
    )

    await executor.job_rune_cex_flow()

    assert captured['period'] == DAY
    assert isinstance(captured['data'], RuneCEXFlow)
    assert captured['data'].total_rune == 17_500.0
    assert captured['data'].period_sec == DAY
    assert captured['data'].infographic_period_sec == 7 * DAY
    assert captured.get('emergency_calls', []) == []


@pytest.mark.asyncio
async def test_rune_transfer_recorder_get_cex_flow_builds_flow_from_summary():
    recorder = RuneTransferRecorder.__new__(RuneTransferRecorder)
    recorder.deps = SimpleNamespace(
        pool_cache=SimpleNamespace(get_usd_per_rune=lambda: None)
    )

    async def fake_get_usd_per_rune():
        return 3.5

    async def fake_get_summary(days, end_ts=None):
        assert days == 2
        return {
            'cex_transfer_count': 4,
            'cex_inflow_rune': 12_345.0,
            'cex_outflow_rune': 234.0,
        }

    recorder.deps.pool_cache.get_usd_per_rune = fake_get_usd_per_rune
    recorder.get_summary = fake_get_summary

    flow = await recorder.get_cex_flow(period=2 * DAY)

    assert flow.rune_cex_inflow == 12_345.0
    assert flow.rune_cex_outflow == 234.0
    assert flow.total_transfers == 4
    assert flow.usd_per_rune == 3.5
    assert flow.period_sec == 2 * DAY

