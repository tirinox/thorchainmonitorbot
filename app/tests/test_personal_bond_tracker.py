import pytest

from models.node_info import NodeEvent, NodeEventType
from notify.personal.bond import BondTracker
from notify.personal.helpers import NodeOpSetting


def _ev(old, new):
    return NodeEvent('thor1node', NodeEventType.BOND, (old, new))


@pytest.mark.asyncio
async def test_bond_threshold_per_user():
    tracker = BondTracker.__new__(BondTracker)
    # default 10 Rune: dust like "404,163 -> 404,163" is ignored
    assert not await tracker.is_event_ok(_ev(404163.2, 404163.9), 1, {})
    assert await tracker.is_event_ok(_ev(1000.0, 1010.0), 1, {})
    assert await tracker.is_event_ok(_ev(1000.0, 985.0), 1, {})

    custom = {NodeOpSetting.BOND_THRESHOLD: 500}
    assert not await tracker.is_event_ok(_ev(1000.0, 1400.0), 1, custom)
    assert await tracker.is_event_ok(_ev(1000.0, 1500.0), 1, custom)

    assert not await tracker.is_event_ok(_ev(1000.0, 5000.0), 1, {NodeOpSetting.BOND_ON: False})
