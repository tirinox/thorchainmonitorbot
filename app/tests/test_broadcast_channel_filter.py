from types import SimpleNamespace
from typing import cast

import pytest

from lib.config import SubConfig
from lib.depcont import DepContainer
from notify.broadcast import Broadcaster
from notify.channel import ChannelDescriptor


class FakeLocalization:
    def __init__(self, lang: str):
        self.name = lang


class FakeLocalizationManager:
    def get_from_lang(self, lang: str):
        return FakeLocalization(lang)


class FakeGeneralAlertsProc:
    def __init__(self, channels: list[ChannelDescriptor]):
        self.channels = channels

    async def get_general_alerts_channels(self, _settings_manager):
        return list(self.channels)


def make_broadcaster(subscribed_channels: list[ChannelDescriptor] | None = None) -> Broadcaster:
    subscribed_channels = subscribed_channels or []
    cfg = SubConfig({
        'broadcasting': {
            'startup_delay': '0s',
            'channels': [
                {'type': 'telegram', 'name': '@thorchain_alert', 'lang': 'eng'},
                {'type': 'discord', 'name': '123', 'lang': 'eng'},
            ],
        },
        'personal': {
            'rate_limit': {
                'number': 10,
                'period': '1m',
                'cooldown': '5m',
            },
        },
    })
    deps = SimpleNamespace(
        cfg=cfg,
        loc_man=FakeLocalizationManager(),
        gen_alert_settings_proc=FakeGeneralAlertsProc(subscribed_channels),
        settings_manager=object(),
    )
    return Broadcaster(cast(DepContainer, cast(object, deps)))


@pytest.mark.asyncio
async def test_broadcast_to_all_uses_configured_and_subscribed_channels_by_default():
    subscribed_channel = ChannelDescriptor('slack', 'ops-room', 'eng')
    broadcaster = make_broadcaster([subscribed_channel])
    captured = {}

    async def fake_broadcast_to(channels, message, msg_type, **kwargs):
        captured['channels'] = list(channels)
        captured['msg_type'] = msg_type
        captured['message'] = message
        return len(channels)

    broadcaster._broadcast_to = fake_broadcast_to

    result = await broadcaster.broadcast_to_all('public:test', 'hello world')

    assert result is None
    assert captured['msg_type'] == 'public:test'
    assert [channel.short_coded for channel in captured['channels']] == [
        'telegram-@thorchain_alert',
        'discord-123',
        'slack-ops-room',
    ]


@pytest.mark.asyncio
async def test_broadcast_to_all_can_limit_delivery_to_selected_configured_channels():
    subscribed_channel = ChannelDescriptor('slack', 'ops-room', 'eng')
    broadcaster = make_broadcaster([subscribed_channel])
    captured = {}

    async def fake_broadcast_to(channels, message, msg_type, **kwargs):
        captured['channels'] = list(channels)
        return len(channels)

    broadcaster._broadcast_to = fake_broadcast_to

    with broadcaster.override_channels(['telegram-@thorchain_alert', {'type': 'discord', 'name': '123'}]):
        result = await broadcaster.broadcast_to_all('public:test', 'hello world')

    assert result is None
    assert [channel.short_coded for channel in captured['channels']] == [
        'telegram-@thorchain_alert',
        'discord-123',
    ]

