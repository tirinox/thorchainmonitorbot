from typing import List

import ujson

from services.jobs.fetch.thormon import ThorMonAnswer
from services.lib.date_utils import MINUTE
from services.lib.depcont import DepContainer
from services.models.time_series import TimeSeries


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

    async def read_telemetry(self, node_addresses: List[str], ago_sec: float, tolerance=MINUTE):
        results = {}
        for node_address in node_addresses:
            series = TimeSeries(self.time_series_key(node_address), self.deps.db)
            best_point, _ = await series.get_best_point_ago(ago_sec, tolerance)
            if best_point:
                best_point = ujson.loads(best_point['json'])
            results[node_address] = best_point
        return results

    # async def