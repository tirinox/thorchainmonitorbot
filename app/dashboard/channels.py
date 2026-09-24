from typing import Any

from notify.channel import ChannelDescriptor


def channel_to_dict(channel: ChannelDescriptor) -> dict[str, str]:
    return {
        'type': str(channel.type).strip().lower(),
        'channel': str(channel.channel_id),
        'lang': str(channel.lang),
        'selector': channel.short_coded,
    }


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
        return bool(channel_type and channel_name) and channel.type == channel_type and str(
            channel.channel_id) == channel_name

    if isinstance(selector, tuple) and len(selector) == 2:
        channel_type = str(selector[0]).strip().lower()
        channel_name = str(selector[1]).strip()
        return bool(channel_type and channel_name) and channel.type == channel_type and str(
            channel.channel_id) == channel_name

    selector = str(selector).strip()
    return bool(selector) and (selector == channel.short_coded or selector == str(channel.channel_id))


def resolve_job_channels(raw_channels: Any,
                         configured_channels: list[ChannelDescriptor]) -> tuple[list[ChannelDescriptor], list[Any]]:
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
