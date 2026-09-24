from notify.channel import ChannelDescriptor
from dashboard.channels import (
    channel_to_dict,
    resolve_job_channels,
    selected_channel_short_codes,
    format_unknown_channel,
)


CONFIGURED_CHANNELS = [
    ChannelDescriptor('telegram', '@thorchain_alert', 'eng'),
    ChannelDescriptor('discord', '123', 'rus'),
    ChannelDescriptor('twitter', 'twitter-default', 'eng-tw'),
]


def test_channel_to_dict_include_selector_and_lang():
    assert channel_to_dict(CONFIGURED_CHANNELS[0]) == {
        'type': 'telegram',
        'channel': '@thorchain_alert',
        'lang': 'eng',
        'selector': 'telegram-@thorchain_alert',
    }


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

