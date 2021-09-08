from typing import List

import ujson

from services.models.thormon import ThorMonNode, ThorMonAnswer, ThorMonNodeTimeSeries
from services.lib.date_utils import MINUTE, HOUR
from services.lib.depcont import DepContainer
from services.models.time_series import TimeSeries


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

            await self.get_series(node.node_address).add(
                json=ujson.dumps(node.original_dict)
            )

    def get_series(self, node_address):
        return TimeSeries(self.time_series_key(node_address), self.deps.db)

    async def read_telemetry_at_timestamp(self, node_addresses: List[str], ago_sec: float, tolerance=MINUTE):
        results = {}
        for node_address in node_addresses:
            best_point, _ = await self.get_series(node_address).get_best_point_ago(ago_sec, tolerance)
            if best_point:
                best_point = ujson.loads(best_point['json'])
            results[node_address] = best_point
        return results

    async def read_telemetry(self, node_address, max_ago_sec: float = HOUR, tolerance=MINUTE,
                             n_points=10_000) -> ThorMonNodeTimeSeries:
        series = self.get_series(node_address)
        points = await series.get_last_values_json(max_ago_sec, tolerance_sec=tolerance, with_ts=True,
                                                   max_points=n_points)
        return [(ts, ThorMonNode.from_json(j)) for ts, j in points]
