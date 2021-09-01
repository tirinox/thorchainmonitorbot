from itertools import takewhile
from typing import List, NamedTuple, Tuple

import ujson

from services.jobs.fetch.thormon import ThorMonAnswer, ThorMonNode
from services.lib.date_utils import MINUTE, HOUR
from services.lib.depcont import DepContainer
from services.models.time_series import TimeSeries

MAX_HISTORY_DURATION = HOUR

HISTORY_DURATION_GRADES = [
    MINUTE,
    5 * MINUTE,
    15 * MINUTE,
    HOUR
]


TimeStampedList = List[Tuple[float, bool]]


class ServiceOnlineProfile(NamedTuple):
    service: str
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
        filtered_points = [(ts, p) for ts, p in self.points if ts > youngest_ts - max_age_sec]
        return self.from_points(filtered_points, self.service)

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


class NodeOnlineProfile(NamedTuple):
    node_address: str
    rpc: ServiceOnlineProfile
    thor: ServiceOnlineProfile
    midgard: ServiceOnlineProfile
    bifrost: ServiceOnlineProfile


class NodeTelemetryDatabase:
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.previous_nodes = {}

    @staticmethod
    def time_series_key(node_address: str):
        return f'NodeTelemetry:{node_address}'

    async def write_telemetry(self, thormon: ThorMonAnswer):
        self.previous_nodes = {}
        for node in thormon.nodes:
            if not node.node_address:
                continue

            self.previous_nodes[node.node_address] = node

            series = TimeSeries(self.time_series_key(node.node_address), self.deps.db)
            await series.add(
                json=ujson.dumps(node.original_dict)
            )

    def get_series(self, node_address):
        return TimeSeries(self.time_series_key(node_address), self.deps.db)

    async def read_telemetry(self, node_addresses: List[str], ago_sec: float, tolerance=MINUTE):
        results = {}
        for node_address in node_addresses:
            best_point, _ = await self.get_series(node_address).get_best_point_ago(ago_sec, tolerance)
            if best_point:
                best_point = ujson.loads(best_point['json'])
            results[node_address] = best_point
        return results

    async def get_online_profiles(self, node_addresses: List[str], max_ago_sec: float = HOUR, tolerance=MINUTE):
        results = {}
        for node_address in node_addresses:
            results[node_address] = await self.get_online_profile(node_address, max_ago_sec, tolerance)
        return results

    async def get_online_profile(self, node_address: str, max_ago_sec: float = HOUR, tolerance=MINUTE):
        series = self.get_series(node_address)
        points = await series.get_last_values_json(max_ago_sec, tolerance_sec=tolerance, with_ts=True)
        node_points = [(ts, ThorMonNode.from_json(j)) for ts, j in points]
        return NodeOnlineProfile(
            node_address,
            rpc=ServiceOnlineProfile.from_thormon_nodes(node_points, 'rpc'),
            midgard=ServiceOnlineProfile.from_thormon_nodes(node_points, 'midgard'),
            bifrost=ServiceOnlineProfile.from_thormon_nodes(node_points, 'bifrost'),
            thor=ServiceOnlineProfile.from_thormon_nodes(node_points, 'thor'),
        )

    async def get_changes(self, node_address):
        if not node_address:
            return []

        changes = []

        profile = await self.get_online_profile(node_address,
                                                max_ago_sec=MAX_HISTORY_DURATION,
                                                tolerance=MAX_HISTORY_DURATION / 60.0)

        return changes
