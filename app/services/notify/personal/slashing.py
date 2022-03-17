import asyncio
from typing import List, Optional

from services.lib.date_utils import MINUTE, parse_timespan_to_seconds
from services.lib.depcont import DepContainer
from services.lib.utils import class_logger
from services.models.node_info import NodeEvent, NodeEventType, EventDataSlash
from services.models.thormon import ThorMonAnswer
from services.models.time_series import TimeSeries
from services.notify.personal.helpers import BaseChangeTracker, NodeOpSetting, STANDARD_INTERVALS
from services.notify.personal.user_data import UserDataCache


class SlashPointTracker(BaseChangeTracker):
    HISTORY_MAX_POINTS = 100_000

    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.series = TimeSeries('SlashPointTracker', self.deps.db)  # fixme! too much memory!!!
        self.std_intervals_sec = [parse_timespan_to_seconds(s) for s in STANDARD_INTERVALS]
        self.logger = class_logger(self)
        intervals = list(zip(STANDARD_INTERVALS, self.std_intervals_sec))
        self.logger.info(f'{intervals = }')
        self.cache: Optional[UserDataCache] = None

    @staticmethod
    def _extract_slash_points(last_answer: ThorMonAnswer):
        return {n.node_address: n.slash_points for n in last_answer.nodes if n.node_address}

    async def _save_point(self, last_answer: ThorMonAnswer):
        data = self._extract_slash_points(last_answer)
        if data:
            await self.series.add(**data)
        await self.series.trim_oldest(self.HISTORY_MAX_POINTS)

    async def _read_points(self, intervals):
        tasks = [
            self.series.get_best_point_ago(ago, tolerance_percent=1, tolerance_sec=20)
            for ago in intervals
        ]
        return await asyncio.gather(*tasks)

    async def get_events(self, last_answer: ThorMonAnswer, user_cache: UserDataCache) -> List[NodeEvent]:
        self.cache = user_cache
        await self._save_point(last_answer)

        points = await self._read_points(intervals=self.std_intervals_sec)
        current_state = self._extract_slash_points(last_answer)

        node_map = last_answer.address_to_node_map

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
                        thor_node=node
                    ))

        return events

    KEY_SERVICE = 'slashing'

    async def is_event_ok(self, event: NodeEvent, user_id, settings: dict) -> bool:
        if not self.cache:
            return False

        if not bool(settings.get(NodeOpSetting.SLASH_ON, True)):
            return False

        # # fixme: ---- 8< ----
        # if event.address == 'thor1dq5tumtlgua3nyp2at0m2jw84ete6jp9ywxyf8':
        #     print('??!')  # todo: test & fix Slash Tracker using the simulation file
        # # fixme: ---- 8< ----

        data: EventDataSlash = event.data

        interval = settings.get(NodeOpSetting.SLASH_PERIOD, 5 * MINUTE)
        if interval != data.interval_sec:
            return False

        threshold = settings.get(NodeOpSetting.SLASH_THRESHOLD, 50)

        if data.delta_pts >= threshold:
            if self.cache.cooldown_can_do(user_id, event.thor_node.node_address,
                                          self.KEY_SERVICE, interval_sec=interval,
                                          do=True):
                return True

        return False
