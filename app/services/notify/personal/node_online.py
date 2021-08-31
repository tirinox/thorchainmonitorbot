from itertools import takewhile
from typing import List, NamedTuple

import ujson

from services.jobs.fetch.thormon import ThorMonAnswer, ThorMonNode
from services.lib.date_utils import MINUTE, HOUR
from services.lib.depcont import DepContainer
from services.models.time_series import TimeSeries


class ServiceOnlineProfile(NamedTuple):
    service: str
    num_points: int
    num_online_points: int
    num_last_silent_points: int
    online_ratio: float
    recent_offline_ratio: float

    @classmethod
    def from_thormon_nodes(cls, data: List[ThorMonNode], service):
        points = [getattr(node, service) for node in data]
        return cls.from_points(points, service)

    @classmethod
    def from_points(cls, points: List[bool], service):
        num_online_points = sum(1 for p in points if p)
        num_points = len(points)
        if not num_points:
            return cls(service, 0, 0, 0, 0, 0)

        online_ratio = num_online_points / num_points
        num_last_silent_points = sum(1 for _ in takewhile(lambda e: not e, reversed(points)))
        recent_offline_ratio = num_last_silent_points / num_points

        return cls(
            service,
            num_points, num_online_points, num_last_silent_points,
            online_ratio, recent_offline_ratio
        )


class NodeOnlineProfile(NamedTuple):
    node_address: str
    rpc: ServiceOnlineProfile
    thor: ServiceOnlineProfile
    midgard: ServiceOnlineProfile
    bifrost: ServiceOnlineProfile


class NodeOnlineTracker:
    def __init__(self, deps: DepContainer):
        self.deps = deps

    @staticmethod
    def time_series_key(node_address: str):
        return f'NodeOnline:{node_address}'

    async def write_telemetry(self, thormon: ThorMonAnswer):
        for node in thormon.nodes:
            if not node.node_address:
                continue
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

    @staticmethod
    def _make_profile(node_address, points: List):
        answers = [ThorMonNode.from_json(j) for j in points]

        return NodeOnlineProfile(
            node_address
        )

    async def get_online_profile(self, node_addresses: List[str], max_ago_sec: float = HOUR, tolerance=MINUTE):
        results = {}
        for node_address in node_addresses:
            series = self.get_series(node_address)
            points = await series.get_last_values_json(max_ago_sec, tolerance_sec=tolerance)
            results[node_address] = self._make_profile(node_address, points)
        return results

    # async def
