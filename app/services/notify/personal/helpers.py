from typing import List, Any, Tuple

from services.lib.date_utils import now_ts
from services.models.node_info import NodeEvent, NodeEventType


class NodeOpSetting:
    IP_ADDRESS_ON = 'nop:ip:on'
    VERSION_ON = 'nop:version:on'
    NEW_VERSION_ON = 'nop:new_v:on'
    BOND_ON = 'nop:bond:on'
    OFFLINE_ON = 'nop:offline:on'
    OFFLINE_INTERVAL = 'nop:offline:interval'
    CHAIN_HEIGHT_ON = 'nop:height:on'
    CHAIN_HEIGHT_INTERVAL = 'nop:height:interval'
    CHURNING_ON = 'nop:churning:on'
    SLASH_ON = 'nop:slash:on'
    SLASH_THRESHOLD = 'nop:slash:threshold'
    SLASH_PERIOD = 'nop:slash:period'


class BaseChangeTracker:
    async def is_event_ok(self, event: NodeEvent, settings: dict) -> bool:
        return True


def get_points_at_time_points(data: List[Tuple[float, Any]], ago_sec_list: list):
    if not ago_sec_list or not data:
        return {}

    now = now_ts()
    results = {}
    ago_list_pos = 0
    for ts, data in reversed(data):  # from new to older
        current_ago = ago_sec_list[ago_list_pos]
        if ts < now - current_ago:
            results[current_ago] = ts, data
            ago_list_pos += 1
            if ago_list_pos >= len(ago_sec_list):
                break
    return results
