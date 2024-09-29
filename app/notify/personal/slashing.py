import asyncio
from typing import List

from lib.date_utils import MINUTE, parse_timespan_to_seconds
from lib.depcont import DepContainer
from lib.utils import WithLogger
from models.node_info import NodeEvent, NodeEventType, EventDataSlash, NodeInfo
from models.time_series import TimeSeries
from notify.personal.helpers import BaseChangeTracker, NodeOpSetting, STANDARD_INTERVALS


class SlashPointTracker(BaseChangeTracker, WithLogger):
    HISTORY_MAX_POINTS = 100_000
    EXTRA_COOLDOWN_MULT = 1.1

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.series = TimeSeries('SlashPointTracker', self.deps.db, self.HISTORY_MAX_POINTS)
        self.std_intervals_sec = [parse_timespan_to_seconds(s) for s in STANDARD_INTERVALS]
        intervals = list(zip(STANDARD_INTERVALS, self.std_intervals_sec))
        self.logger.info(f'{intervals = }')

    @staticmethod
    def _extract_slash_points(nodes: List[NodeInfo]):
        return {n.node_address: n.slash_points for n in nodes if n.node_address}

    async def _save_point(self, nodes: List[NodeInfo]):
        data = self._extract_slash_points(nodes)
        if data:
            await self.series.add(**data)
        # await self.series.trim_oldest(self.HISTORY_MAX_POINTS)

    async def _read_points(self, intervals):
        tasks = [
            self.series.get_best_point_ago(ago, tolerance_percent=1, tolerance_sec=20)
            for ago in intervals
        ]
        return await asyncio.gather(*tasks)

    async def get_events_unsafe(self) -> List[NodeEvent]:
        nodes = self.node_set_change.nodes_all

        await self._save_point(nodes)

        points = await self._read_points(intervals=self.std_intervals_sec)
        current_state = self._extract_slash_points(nodes)

        node_map = {node.node_address: node for node in nodes}

        events = []
        for interval, (data, _) in zip(self.std_intervals_sec, points):
            if data is None:
                continue

            for address, slash_pts in data.items():
                node = node_map.get(address)
                if not node:
                    continue

                slash_pts = int(slash_pts)
                current_slash_pts = int(current_state.get(address, 0))
                if slash_pts != current_slash_pts:
                    events.append(NodeEvent(
                        address, NodeEventType.SLASHING,
                        EventDataSlash(slash_pts, current_slash_pts, interval),
                        tracker=self,
                        node=node
                    ))

        return events

    KEY_SERVICE = 'slashing'

    async def is_event_ok(self, event: NodeEvent, user_id, settings: dict) -> bool:
        if not self.user_cache:
            return False

        if not bool(settings.get(NodeOpSetting.SLASH_ON, True)):
            return False

        data: EventDataSlash = event.data

        interval = settings.get(NodeOpSetting.SLASH_PERIOD, 5 * MINUTE)
        if interval != data.interval_sec:
            return False

        threshold = settings.get(NodeOpSetting.SLASH_THRESHOLD, 1000)

        if data.delta_pts >= threshold:
            cd = interval * self.EXTRA_COOLDOWN_MULT
            if self.user_cache.cooldown_can_do(user_id, event.address,
                                               self.KEY_SERVICE, interval_sec=cd,
                                               do=True):
                return True

        return False
