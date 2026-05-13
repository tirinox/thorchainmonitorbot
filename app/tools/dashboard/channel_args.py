from typing import Any

from notify.channel import ChannelDescriptor

CHANNEL_TYPE_ICONS = {
    'telegram': '✈️',
    'discord': '🎮',
    'slack': '💬',
    'twitter': '🐦',
}


def channel_icon(channel_type: str) -> str:
    return CHANNEL_TYPE_ICONS.get(str(channel_type).strip().lower(), '📣')


def channel_type_title(channel_type: str) -> str:
    channel_type = str(channel_type).strip().lower()
    return channel_type.capitalize() if channel_type else 'Unknown'


def channel_selector_label(channel: ChannelDescriptor) -> str:
    return (
        f"{channel_icon(channel.type)} {channel_type_title(channel.type)}"
        f" · {channel.channel_id} · lang={channel.lang}"
    )


def configured_channel_rows(channels: list[ChannelDescriptor]) -> list[dict[str, str]]:
    return [
        {
            'Type': f"{channel_icon(channel.type)} {channel_type_title(channel.type)}",
            'Channel': str(channel.channel_id),
            'Lang': str(channel.lang),
            'Selector': channel.short_coded,
        }
        for channel in channels
    ]


def coerce_channel_items(raw_channels: Any) -> list[Any]:
    if raw_channels is None:
        return []
    if isinstance(raw_channels, (list, tuple, set)):
        return list(raw_channels)
    return [raw_channels]


def _matches_channel(channel: ChannelDescriptor, selector: Any) -> bool:
    if isinstance(selector, dict):
        channel_type = str(selector.get('type', '')).strip().lower()
        channel_name = str(selector.get('name', '')).strip()
        return bool(channel_type and channel_name) and channel.type == channel_type and str(channel.channel_id) == channel_name

    if isinstance(selector, tuple) and len(selector) == 2:
        channel_type = str(selector[0]).strip().lower()
        channel_name = str(selector[1]).strip()
        return bool(channel_type and channel_name) and channel.type == channel_type and str(channel.channel_id) == channel_name

    selector = str(selector).strip()
    return bool(selector) and (selector == channel.short_coded or selector == str(channel.channel_id))


def resolve_job_channels(raw_channels: Any, configured_channels: list[ChannelDescriptor]) -> tuple[list[ChannelDescriptor], list[Any]]:
    resolved: list[ChannelDescriptor] = []
    unresolved: list[Any] = []
    seen = set()

    for item in coerce_channel_items(raw_channels):
        matches = [channel for channel in configured_channels if _matches_channel(channel, item)]
        if not matches:
            unresolved.append(item)
            continue

        for channel in matches:
            if channel.short_coded in seen:
                continue
            resolved.append(channel)
            seen.add(channel.short_coded)

    return resolved, unresolved


def selected_channel_short_codes(raw_channels: Any, configured_channels: list[ChannelDescriptor]) -> list[str]:
    resolved, _ = resolve_job_channels(raw_channels, configured_channels)
    return [channel.short_coded for channel in resolved]


def format_unknown_channel(selector: Any) -> str:
    if isinstance(selector, dict):
        channel_type = str(selector.get('type', '')).strip().lower()
        channel_name = str(selector.get('name', '')).strip()
        if channel_type or channel_name:
            return f"{channel_type or '?'}:{channel_name or '?'}"
    if isinstance(selector, tuple) and len(selector) == 2:
        return f"{selector[0]}:{selector[1]}"
    return str(selector)

