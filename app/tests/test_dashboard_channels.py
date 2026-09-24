from notify.channel import ChannelDescriptor
from tools.dashboard.channel_args import (
    configured_channel_rows,
    resolve_job_channels,
    selected_channel_short_codes,
    format_unknown_channel,
)


CONFIGURED_CHANNELS = [
    ChannelDescriptor('telegram', '@thorchain_alert', 'eng'),
    ChannelDescriptor('discord', '123', 'rus'),
    ChannelDescriptor('twitter', 'twitter-default', 'eng-tw'),
]


def test_configured_channel_rows_include_selector_and_lang():
    rows = configured_channel_rows(CONFIGURED_CHANNELS)

    assert rows[0]['Type'].startswith('✈️ Telegram')
    assert rows[0]['Channel'] == '@thorchain_alert'
    assert rows[0]['Lang'] == 'eng'
    assert rows[0]['Selector'] == 'telegram-@thorchain_alert'


def test_resolve_job_channels_supports_short_codes_and_object_selectors():
    resolved, unresolved = resolve_job_channels(
        ['telegram-@thorchain_alert', {'type': 'discord', 'name': '123'}],
        CONFIGURED_CHANNELS,
    )

    assert [channel.short_coded for channel in resolved] == [
        'telegram-@thorchain_alert',
        'discord-123',
    ]
    assert unresolved == []


def test_selected_channel_short_codes_support_plain_channel_id_and_ignore_unknown_entries():
    selected = selected_channel_short_codes(
        ['@thorchain_alert', 'missing-channel'],
        CONFIGURED_CHANNELS,
    )

    assert selected == ['telegram-@thorchain_alert']


def test_resolve_job_channels_returns_unknown_entries_for_display():
    resolved, unresolved = resolve_job_channels(
        ['telegram-@thorchain_alert', 'missing-channel', {'type': 'slack', 'name': 'ops'}],
        CONFIGURED_CHANNELS,
    )

    assert [channel.short_coded for channel in resolved] == ['telegram-@thorchain_alert']
    assert [format_unknown_channel(item) for item in unresolved] == ['missing-channel', 'slack:ops']

