from types import SimpleNamespace

import pytest
from PIL import Image

from lib.date_utils import DAY
from models.transfer import RuneCEXFlow
from notify.alert_presenter import AlertPresenter
from notify.channel import MessageType


class FakeRecorder:
    def __init__(self, deps):
        self.deps = deps

    async def get_summary(self, days):
        self.days = days
        return {
            'days': days,
            'start_date': '2026-04-12',
            'end_date': '2026-04-13',
            'volume_rune': 1234.5,
            'transfer_count': 3,
            'cex_inflow_rune': 1000.0,
            'cex_outflow_rune': 234.5,
            'cex_inflow_count': 2,
            'cex_outflow_count': 1,
            'cex_netflow_rune': 765.5,
            'daily': [],
        }


class FakeBroadcaster:
    def __init__(self):
        self.calls = []
        self.last_message = None

    async def broadcast_to_all(self, msg_type, message_gen, *args, **kwargs):
        self.calls.append((msg_type, message_gen, args, kwargs))
        loc = SimpleNamespace(
            name='en',
            notification_text_rune_transfer_stats=lambda data: f'CEX flow: {data.transfer_count} transfers',
        )
        self.last_message = await message_gen(loc)
        return self.last_message


@pytest.mark.asyncio
async def test_rune_cex_flow_broadcasts_infographic(monkeypatch):
    broadcaster = FakeBroadcaster()
    presenter = AlertPresenter.__new__(AlertPresenter)
    presenter.deps = SimpleNamespace(broadcaster=broadcaster)
    presenter.broadcaster = broadcaster

    async def fake_render(self, loc, data):
        assert data.period_days == 2
        assert data.usd_per_rune == 3.21
        return Image.new('RGB', (2, 2), 'white'), 'rune_transfer_stats.png'

    monkeypatch.setattr(AlertPresenter, 'render_rune_transfer_stats', fake_render)
    monkeypatch.setattr('notify.alert_presenter.RuneTransferRecorder', FakeRecorder)

    flow = RuneCEXFlow(
        rune_cex_inflow=1000.0,
        rune_cex_outflow=234.5,
        total_transfers=3,
        usd_per_rune=3.21,
        period_sec=2 * DAY,
    )

    await presenter._handle_rune_cex_flow(flow)

    assert broadcaster.calls
    msg_type, _, _, _ = broadcaster.calls[0]
    assert msg_type == 'public:rune_cex_flow'

    message = broadcaster.last_message
    assert message.message_type == MessageType.PHOTO
    assert message.photo_file_name == 'rune_transfer_stats.png'
    assert message.photo is not None
    assert 'CEX flow: 3 transfers' in message.text

