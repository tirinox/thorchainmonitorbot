from typing import List

from services.lib.depcont import DepContainer
from services.models.node_info import MapAddressToPrevAndCurrNode, NodeChangeType, NodeChange, STANDARD_INTERVALS, \
    ChangeVariation
from services.models.thormon import ThorMonNodeTimeSeries
from services.notify.personal.helpers import BaseChangeTracker, get_points_at_time_points

"""
User selects a time period (5min, 15min, 1h)
And threshold (e.g. 5 pts)

if not cooldown and now.slash - [5min ago].slash > threshold:
    emit notification
    start cooldown
"""


class SlashPointTracker(BaseChangeTracker):
    def __init__(self, deps: DepContainer):
        self.deps = deps

    def get_slash_changes(self, telemetry: ThorMonNodeTimeSeries):
        node_states = get_points_at_time_points(telemetry, STANDARD_INTERVALS)
        last_point = telemetry[-1][1]
        return ChangeVariation(last_point.slash_points, previous_values=node_states)

    async def get_node_changes(self, node_address, telemetry: ThorMonNodeTimeSeries) -> List[NodeChange]:
        node_states = get_points_at_time_points(telemetry, STANDARD_INTERVALS)
        return []

    # async def get_all_changes(self, pc_node_map: MapAddressToPrevAndCurrNode) -> List[NodeChange]:
    #     changes = []
    #     for a, (prev, curr) in pc_node_map.items():
    #         delta_slash = curr.slash_points - prev.slash_points
    #         if delta_slash != 0:
    #             changes.append(
    #                 NodeChange(
    #                     prev.node_address, NodeChangeType.SLASHING, (prev.slash_points, curr.slash_points)
    #                 )
    #             )
    #     return changes

    async def filter_changes(self, ch_list: List[NodeChange], settings: dict) -> List[NodeChange]:
        return await super().filter_changes(ch_list, settings)
