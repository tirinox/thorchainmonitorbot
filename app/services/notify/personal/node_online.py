from typing import List, Tuple

from services.lib.date_utils import HOUR
from services.lib.depcont import DepContainer
from services.models.node_info import EventNodeOnline, NodeEvent
from services.models.thormon import ThorMonAnswer
from services.notify.personal import UserDataCache
from services.notify.personal.helpers import BaseChangeTracker, NodeOpSetting
from services.notify.personal.telemetry import NodeTelemetryDatabase

TimeStampedList = List[Tuple[float, bool]]

SERVICES = ['rpc', 'midgard', 'thor', 'bifrost']


class NodeOnlineTracker(BaseChangeTracker):
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.telemetry_db = NodeTelemetryDatabase(deps)

    async def get_node_events(self, node_address, last_answer: ThorMonAnswer, user_cache: UserDataCache):
        if not node_address:
            return []


        # events = self.data.update(last_answer.nodes, ref_ts=now_ts())
        # await self.data.save(self.deps.db)

        return events

    async def is_event_ok(self, event: NodeEvent, user_id, settings: dict) -> bool:
        if not bool(settings.get(NodeOpSetting.OFFLINE_ON, True)):
            return False

        event_data: EventNodeOnline = event.data
        threshold_interval = float(settings.get(NodeOpSetting.OFFLINE_INTERVAL, HOUR))

        return True

"""

    # def last_online_ts(self, node: str, service: str):
    #     try:
    #         return self.node_service_last_online_ts[node][service]
    #     except LookupError:
    #         return 0

    # def offline_time(self, node: str, service: str, ts=None):
    #     ref_ts = ts or now_ts()
    #     return ref_ts - self.last_online_ts(node, service)


    def update(self, nodes: List[ThorMonNode], ref_ts=None):
        ref_ts = ref_ts or now_ts()
        cache = self.node_service_last_online_ts
        events = []
        for node in nodes:
            address = node.node_address
            for service in SERVICES:
                is_ok = bool(getattr(node, service))
                if is_ok:
                    if address not in cache:
                        cache[address] = {}
                    cache[address][service] = ref_ts()

                events.append(NodeEvent(
                    address,
                    NodeEventType.SERVICE_ONLINE,
                    EventNodeOnline(is_ok, self.offline_time(address, service, ref_ts), service),
                    thor_node=node,
                    tracker=self
                ))
        return events

    def is_online_tracked(self, user, node, service, default=True):
        try:
            return self.user_node_service_is_online[user][node][service]
        except LookupError:
            return default

    def set_online_tracked(self, user, node, service, online_flag):
        cache = self.user_node_service_is_online
        if user not in cache:
            cache[user] = {}
        if node not in cache[user]:
            cache[user][node] = {}
        cache[user][node][service] = online_flag

"""