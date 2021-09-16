from typing import List, Any, Tuple

from services.lib.date_utils import now_ts
from services.models.node_info import NodeChange


class NodeOpSetting:
    VERSION = 'nop:version:on'
    NEW_VERSION = 'nop:new_v:on'
    BOND = 'nop:bond:on'
    OFFLINE = 'nop:offline:on'
    CHAIN_HEIGHT = 'nop:height:on'
    CHURNING = 'nop:churning:on'
    SLASH = 'nop:slash:on'
    SLASH_THRESHOLD = 'nop:slash:threshold'
    SLASH_PERIOD = 'nop:slash:period'


class BaseChangeTracker:
    async def filter_changes(self, ch_list: List[NodeChange], settings: dict) -> List[NodeChange]:
        return ch_list


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
