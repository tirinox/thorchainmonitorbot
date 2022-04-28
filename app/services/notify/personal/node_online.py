import time
from typing import List, Tuple

from services.jobs.poll_tcp import TCPPollster
from services.lib.constants import THORPort
from services.lib.date_utils import HOUR, now_ts, DAY
from services.lib.depcont import DepContainer
from services.lib.utils import class_logger
from services.models.node_info import EventNodeOnline, NodeEvent, NodeEventType
from services.notify.personal.helpers import BaseChangeTracker, NodeOpSetting
from services.notify.personal.telemetry import NodeTelemetryDatabase

TimeStampedList = List[Tuple[float, bool]]

RPC = 'rpc'
BIFROST = 'bifrost'
SERVICES = [RPC, BIFROST]

AGE_CUT_OFF = 30 * DAY


class NodeOnlineTracker(BaseChangeTracker):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.telemetry_db = NodeTelemetryDatabase(deps)

        self.logger = class_logger(self)

        cfg = deps.cfg.get('node_op_tools.types.online_service')
        timeout = cfg.as_float('tcp_timeout', 1.0)
        self.pollster = TCPPollster(loop=deps.loop, test_timeout=timeout)
        self._poll_group_size = cfg.as_int('group_size', 20)

    KEY_LAST_ONLINE_TS = 'last_online_ts'
    KEY_ONLINE_STATE = 'online'

    def get_offline_time(self, node: str, service: str, ts=None):
        ref_ts = ts or now_ts()
        return ref_ts - self.user_cache.node_service_data[node][service].get(self.KEY_LAST_ONLINE_TS, 0)

    def set_offline_time(self, node: str, service: str, ts=None):
        ref_ts = ts or now_ts()
        self.user_cache.node_service_data[node][service][self.KEY_LAST_ONLINE_TS] = ref_ts

    def get_user_state(self, user, node, service):
        return self.user_cache.user_node_service_data[user][node][service].get(self.KEY_ONLINE_STATE, True)

    def set_user_state(self, user, node, service, is_ok):
        self.user_cache.user_node_service_data[user][node][service][self.KEY_ONLINE_STATE] = is_ok

    async def get_events_unsafe(self) -> List[NodeEvent]:
        port_family = THORPort.get_port_family(self.deps.cfg.network_id)

        service_to_port = {
            BIFROST: port_family.BIFROST,
            RPC: port_family.RPC
        }
        port_to_service = {v: k for k, v in service_to_port.items()}

        ip_to_node = {node.ip_address: node for node in self.node_set_change.nodes_all if node.ip_address}

        t0 = time.perf_counter()
        # Structure: dict{str(IP): dict{int(port): bool(is_available)} }
        results = await self.pollster.test_connectivity_multiple(ip_to_node.keys(),
                                                                 port_to_service.keys(),
                                                                 group_size=self._poll_group_size)
        time_elapsed = time.perf_counter() - t0

        stats = self.pollster.count_stats(results)
        self.logger.info(f'TCP Poll results: {stats}, {time_elapsed = :.3f} sec')

        ref_ts = now_ts()
        events = []
        for node_ip, node_results in results.items():
            for port, is_available in node_results.items():
                node = ip_to_node.get(node_ip)
                if not node:
                    continue

                service = port_to_service.get(port)

                address = node.node_address
                if is_available:
                    self.set_offline_time(address, service, ref_ts)

                off_time = self.get_offline_time(address, service, ref_ts)

                if off_time > AGE_CUT_OFF:
                    continue

                events.append(NodeEvent(
                    address,
                    NodeEventType.SERVICE_ONLINE,
                    EventNodeOnline(is_available, off_time, service),
                    node=node,
                    tracker=self
                ))

        return events

    async def is_event_ok(self, event: NodeEvent, user_id, settings: dict) -> bool:
        if not bool(settings.get(NodeOpSetting.OFFLINE_ON, True)):
            return False

        threshold_interval = float(settings.get(NodeOpSetting.OFFLINE_INTERVAL, HOUR))

        event_data: EventNodeOnline = event.data
        if event_data.duration > AGE_CUT_OFF:
            return False

        node, service = event.node.node_address, event_data.service
        user_thinks_online = self.get_user_state(user_id, node, service)

        # # fixme: debug
        # if event.node.node_address == 'thor1krcz33mejvc5f6grj2c5w5x3kuj7mnjhgqltj8':
        #     print(f'!!! {user_thinks_online = }, {user_id = }, {node = }, {event_data.duration = }')

        if user_thinks_online and not event_data.online and event_data.duration >= threshold_interval:
            self.set_user_state(user_id, node, service, False)
            return True

        if not user_thinks_online and event_data.online:
            self.set_user_state(user_id, node, service, True)
            return True

        return False
