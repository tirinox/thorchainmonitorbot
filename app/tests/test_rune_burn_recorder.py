import pytest

from jobs.rune_burn_recorder import RuneBurnRecorder
from lib.constants import ADR23_APPLY_BLOCK, ADR23_MAX_SUPPLY_AFTER_PATCH_RAW, \
    ADR23_MAX_SUPPLY_BEFORE_PATCH_RAW, ADR23_MAX_SUPPLY_PATCH_DELTA_RAW


class _FakeTimeSeries:
    def __init__(self, points):
        self._points = points

    async def get_last_points(self, period_sec):
        return self._points


def test_normalize_max_supply_8_by_block_before_patch():
    assert RuneBurnRecorder.normalize_max_supply_8(
        ADR23_MAX_SUPPLY_BEFORE_PATCH_RAW,
        block=ADR23_APPLY_BLOCK - 1,
    ) == ADR23_MAX_SUPPLY_AFTER_PATCH_RAW


def test_normalize_max_supply_8_keeps_post_patch_value():
    assert RuneBurnRecorder.normalize_max_supply_8(
        ADR23_MAX_SUPPLY_AFTER_PATCH_RAW,
        block=ADR23_APPLY_BLOCK,
    ) == ADR23_MAX_SUPPLY_AFTER_PATCH_RAW


def test_normalize_max_supply_8_legacy_series_without_block_context():
    assert RuneBurnRecorder.normalize_max_supply_8(ADR23_MAX_SUPPLY_BEFORE_PATCH_RAW) == ADR23_MAX_SUPPLY_AFTER_PATCH_RAW
    assert RuneBurnRecorder.normalize_max_supply_8(ADR23_MAX_SUPPLY_AFTER_PATCH_RAW) == ADR23_MAX_SUPPLY_AFTER_PATCH_RAW
    assert ADR23_MAX_SUPPLY_PATCH_DELTA_RAW > 0


@pytest.mark.asyncio
async def test_get_last_supply_dataframe_removes_adr23_artificial_spike():
    recorder = RuneBurnRecorder.__new__(RuneBurnRecorder)
    recorder.tally_period = 3600
    recorder.ts = _FakeTimeSeries([
        ('1700000000000-0', {'max_supply': str(ADR23_MAX_SUPPLY_AFTER_PATCH_RAW), 'normalized': '1'}),
        ('1700000060000-0', {'max_supply': str(ADR23_MAX_SUPPLY_AFTER_PATCH_RAW)}),
    ])

    df = await recorder.get_last_supply_dataframe()

    assert pytest.approx(df['max_supply_delta'].iloc[1], abs=1e-6) == 0.0

