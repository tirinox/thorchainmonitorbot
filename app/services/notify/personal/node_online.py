from itertools import takewhile, islice
from typing import List, NamedTuple, Tuple

from services.models.thormon import ThorMonNode
from services.lib.cooldown import CooldownBiTrigger, INFINITE_TIME
from services.lib.date_utils import MINUTE, HOUR, now_ts
from services.lib.depcont import DepContainer
from services.notify.personal.models import BaseChangeTracker
from services.models.node_info import ChangeOnline, NodeChangeType, NodeChange
from services.notify.personal.telemetry import NodeTelemetryDatabase

MAX_HISTORY_DURATION = HOUR
DETECTION_OFFLINE_TIME = 10.0  # sec
TRIGGER_SWITCH_CD = 30.0  # sec

TimeStampedList = List[Tuple[float, bool]]


class ServiceOnlineProfile(NamedTuple):
    name: str
    num_points: int
    num_online_points: int
    num_last_silent_points: int
    online_ratio: float
    recent_offline_ratio: float
    points: TimeStampedList

    def filter_age(self, max_age_sec):
        if not self.points:
            return self
        youngest_ts = max(ts for ts, p in self.points)
        filtered_points = [(ts, p) for ts, p in self.points if ts >= youngest_ts - max_age_sec]
        return self.from_points(filtered_points, self.name)

    @classmethod
    def from_thormon_nodes(cls, data: List[Tuple[float, ThorMonNode]], service):
        points = [(ts, getattr(node, service)) for ts, node in data]
        return cls.from_points(points, service)

    @classmethod
    def from_points(cls, points: TimeStampedList, service):
        num_online_points = sum(1 for ts, p in points if p)
        num_points = len(points)
        if not num_points:
            return cls(service, 0, 0, 0, 0, 0, [])

        online_ratio = num_online_points / num_points
        num_last_silent_points = sum(1 for _ in takewhile(lambda e: not e[1], reversed(points)))
        recent_offline_ratio = num_last_silent_points / num_points

        return cls(
            service,
            num_points, num_online_points, num_last_silent_points,
            online_ratio, recent_offline_ratio,
            points=points
        )

    def calc_offline_time(self, now=None, skip=0):
        now = now or now_ts()
        youngest_ts = now
        for ts, value in islice(reversed(self.points), skip, None):
            if value:
                break
            youngest_ts = ts
        return now - youngest_ts

    @property
    def offline_time(self):
        return self.calc_offline_time(now_ts())


class NodeOnlineProfile(NamedTuple):
    node_address: str
    rpc: ServiceOnlineProfile
    thor: ServiceOnlineProfile
    midgard: ServiceOnlineProfile
    bifrost: ServiceOnlineProfile


class NodeOnlineTracker(BaseChangeTracker):
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.telemetry_db = NodeTelemetryDatabase(deps)

    async def get_online_profiles(self, node_addresses: List[str], max_ago_sec: float = HOUR, tolerance=MINUTE):
        results = {}
        for node_address in node_addresses:
            results[node_address] = await self.get_online_profile(node_address, max_ago_sec, tolerance)
        return results

    async def get_online_profile(self, node_address: str, max_ago_sec: float = HOUR, tolerance=MINUTE):
        node_points = await self.telemetry_db.read_telemetry(node_address, max_ago_sec, tolerance)
        return NodeOnlineProfile(
            node_address,
            rpc=ServiceOnlineProfile.from_thormon_nodes(node_points, 'rpc'),
            midgard=ServiceOnlineProfile.from_thormon_nodes(node_points, 'midgard'),
            bifrost=ServiceOnlineProfile.from_thormon_nodes(node_points, 'bifrost'),
            thor=ServiceOnlineProfile.from_thormon_nodes(node_points, 'thor'),
        )

    async def get_node_changes(self, node_address, **kwargs):
        if not node_address:
            return []

        changes = []

        profile = await self.get_online_profile(node_address,
                                                max_ago_sec=MAX_HISTORY_DURATION,
                                                tolerance=MAX_HISTORY_DURATION / 60.0)
        for service in (profile.rpc, profile.thor, profile.bifrost, profile.midgard):
            offline = service.offline_time

            # node is considered online by default!
            trigger = CooldownBiTrigger(self.deps.db,
                                        f'online.{service.name}.{node_address}',
                                        cooldown_sec=INFINITE_TIME,
                                        switch_cooldown_sec=TRIGGER_SWITCH_CD,
                                        default=True)

            if offline >= DETECTION_OFFLINE_TIME and await trigger.turn_off():
                changes.append(NodeChange(node_address, NodeChangeType.SERVICE_ONLINE, ChangeOnline(False, offline)))
            elif offline == 0.0 and await trigger.turn_on():
                changes.append(NodeChange(node_address, NodeChangeType.SERVICE_ONLINE, ChangeOnline(True, 0.0)))

        return changes
