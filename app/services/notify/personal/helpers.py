from typing import List, Any, Tuple, Optional

from services.lib.date_utils import now_ts
from services.lib.utils import class_logger
from services.models.node_info import NodeEvent, MapAddressToPrevAndCurrNode, NodeSetChanges
from services.notify.personal.user_data import UserDataCache

STANDARD_INTERVALS = [
    '2m',
    '5m',
    '15m',
    '30m',
    '60m',
    '2h',
    '6h',
    '12h',
    '24h',
    '3d',
]


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
    PAUSE_ALL_ON = 'nop:pause_all:on'

    NODE_PRESENCE = 'nop:presence:on'  # new


class GeneralSettings:
    INACTIVE = '_inactive'

    GENERAL_ALERTS = 'gen:alerts'
    PRICE_DIV_ALERTS = 'personal:price-div'
    VAR_PRICE_DIV_LAST_VALUE = 'personal:price-div:$last'
    LANGUAGE = 'lang'
    BALANCE_TRACK = 'personal:balance-track'

    KEY_ADDRESSES = 'addresses'


class BaseChangeTracker:
    def __init__(self):
        self.logger = class_logger(self)

        self.user_cache: Optional[UserDataCache] = None
        self.prev_and_curr_node_map: MapAddressToPrevAndCurrNode = {}
        self.node_set_change: Optional[NodeSetChanges] = None

    async def is_event_ok(self, event: NodeEvent, user_id, settings: dict) -> bool:
        return True

    async def get_events(self) -> List[NodeEvent]:
        try:
            return await self.get_events_unsafe()
        except Exception:
            self.logger.exception('Failed to get events!', exc_info=True)
            return []

    async def get_events_unsafe(self) -> List[NodeEvent]:
        raise NotImplemented


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
