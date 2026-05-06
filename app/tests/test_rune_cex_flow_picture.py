from types import SimpleNamespace
from typing import cast

import pytest
from PIL import Image

from models.transfer import AlertRuneTransferStats
from notify.alert_presenter import AlertPresenter
from notify.broadcast import Broadcaster
from notify.channel import MessageType


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
async def test_rune_transfer_stats_broadcasts_infographic(monkeypatch):
    broadcaster = FakeBroadcaster()
    presenter = AlertPresenter.__new__(AlertPresenter)
    presenter.deps = SimpleNamespace(broadcaster=broadcaster)
    presenter.broadcaster = cast(Broadcaster, cast(object, broadcaster))

    async def fake_render(self, loc, data):
        assert data.period_days == 7
        assert data.usd_per_rune == 3.21
        return Image.new('RGB', (2, 2), 'white'), 'rune_transfer_stats.png'

    monkeypatch.setattr(AlertPresenter, 'render_rune_transfer_stats', fake_render)

    data = AlertRuneTransferStats(
        period_days=7,
        start_date='2026-04-08',
        end_date='2026-04-14',
        volume_rune=1234.5,
        transfer_count=3,
        cex_inflow_rune=1000.0,
        cex_outflow_rune=234.5,
        cex_inflow_count=2,
        cex_outflow_count=1,
        cex_netflow_rune=765.5,
        usd_per_rune=3.21,
        daily=[],
    )

    await presenter.handle_data(data)

    assert broadcaster.calls
    msg_type, _, _, _ = broadcaster.calls[0]
    assert msg_type == 'public:rune_transfers:stats'

    message = broadcaster.last_message
    assert message.message_type == MessageType.PHOTO
    assert message.photo_file_name == 'rune_transfer_stats.png'
    assert message.photo is not None
    assert 'CEX flow: 3 transfers' in message.text

