from types import SimpleNamespace
from typing import cast

import pytest
from PIL import Image

from lib.texts import shorten_text
from models.mimir import AlertMimirVoting, MimirHolder, MimirVoting, MIMIR_VOTING_PRETTY_NAME_DISPLAY_LIMIT
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


class _DummyMimirRules:
    @staticmethod
    def get_mimir_units(_key):
        return None


class _DummyMimirHolder:
    mimir_rules = _DummyMimirRules()

    def __init__(self, pretty_name):
        self._pretty_name = pretty_name

    @staticmethod
    def get_entry(_key):
        return None

    def pretty_name(self, _key):
        return self._pretty_name


@pytest.mark.asyncio
async def test_rune_transfer_stats_broadcasts_infographic(monkeypatch):
    broadcaster = FakeBroadcaster()
    presenter = cast(AlertPresenter, object.__new__(AlertPresenter))
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


@pytest.mark.asyncio
async def test_render_voting_chart_truncates_pretty_name_before_renderer():
    presenter = cast(AlertPresenter, object.__new__(AlertPresenter))

    class FakeRenderer:
        def __init__(self):
            self.calls = []

        async def render(self, template, payload):
            self.calls.append((template, payload))
            return b'fake-image'

    presenter.renderer = FakeRenderer()

    long_pretty_name = 'This is a very long pretty name for the voting infographic payload'
    event = AlertMimirVoting(
        holder=cast(MimirHolder, cast(object, _DummyMimirHolder(long_pretty_name))),
        voting=MimirVoting('NEXTCHAIN', {}, 100),
    )
    loc = SimpleNamespace(format_mimir_value=lambda key, value, units=None: value)

    photo, photo_name = await presenter.render_voting_chart(loc, event)

    assert photo == b'fake-image'
    assert photo_name == 'mimir_voting.png'
    assert presenter.renderer.calls

    template, payload = presenter.renderer.calls[0]
    assert template == 'mimir_voting.jinja2'
    assert payload['pretty_name'] == shorten_text(long_pretty_name, MIMIR_VOTING_PRETTY_NAME_DISPLAY_LIMIT)
    assert len(payload['pretty_name']) == MIMIR_VOTING_PRETTY_NAME_DISPLAY_LIMIT


