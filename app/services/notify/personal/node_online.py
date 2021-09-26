from typing import List, Tuple, Optional

from services.lib.date_utils import HOUR, now_ts
from services.lib.depcont import DepContainer
from services.models.node_info import EventNodeOnline, NodeEvent, NodeEventType
from services.models.thormon import ThorMonAnswer, ThorMonNode
from services.notify.personal import UserDataCache
from services.notify.personal.helpers import BaseChangeTracker, NodeOpSetting
from services.notify.personal.telemetry import NodeTelemetryDatabase

TimeStampedList = List[Tuple[float, bool]]

SERVICES = ['rpc', 'midgard', 'thor', 'bifrost']


class NodeOnlineTracker(BaseChangeTracker):
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.telemetry_db = NodeTelemetryDatabase(deps)
        self.cache: Optional[UserDataCache] = None

    KEY_LAST_ONLINE_TS = 'last_online_ts'
    KEY_ONLINE_STATE = 'online'

    def get_offline_time(self, node: str, service: str, ts=None):
        ref_ts = ts or now_ts()
        return ref_ts - self.cache.node_service_data[node][service].get(self.KEY_LAST_ONLINE_TS, 0)

    def get_user_state(self, user, node, service):
        return self.cache.user_node_service_data[user][node][service].get(self.KEY_ONLINE_STATE, True)

    def set_user_state(self, user, node, service, is_ok):
        return self.cache.user_node_service_data[user][node][service].get(self.KEY_ONLINE_STATE, is_ok)

    def _update(self, nodes: List[ThorMonNode], ref_ts=None):
        ref_ts = ref_ts or now_ts()
        events = []
        for node in nodes:
            address = node.node_address
            for service in SERVICES:
                is_ok = bool(getattr(node, service))

                if is_ok:
                    self.cache.node_service_data[node][service][self.KEY_LAST_ONLINE_TS] = ref_ts

                events.append(NodeEvent(
                    address,
                    NodeEventType.SERVICE_ONLINE,
                    EventNodeOnline(is_ok, self.get_offline_time(address, service, ref_ts), service),
                    thor_node=node,
                    tracker=self
                ))
        return events

    async def get_events(self, last_answer: ThorMonAnswer, user_cache: UserDataCache):
        self.cache = user_cache
        return self._update(last_answer.nodes, now_ts())

    async def is_event_ok(self, event: NodeEvent, user_id, settings: dict) -> bool:
        if not bool(settings.get(NodeOpSetting.OFFLINE_ON, True)):
            return False

        threshold_interval = float(settings.get(NodeOpSetting.OFFLINE_INTERVAL, HOUR))

        event_data: EventNodeOnline = event.data
        node, service = event.thor_node.node_address, event_data.service
        user_thinks_online = self.get_user_state(user_id, node, service)

        if user_thinks_online and not event_data.online and event_data.duration >= threshold_interval:
            self.set_user_state(user_id, node, service, False)
            return True

        if not user_thinks_online and event_data.online:
            self.set_user_state(user_id, node, service, True)
            return True

        return False
