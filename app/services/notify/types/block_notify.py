from typing import Dict, Optional

from aiothornode.types import ThorLastBlock

from services.jobs.fetch.base import INotified
from services.lib.cooldown import Cooldown
from services.lib.date_utils import DAY, MINUTE
from services.lib.depcont import DepContainer
from services.lib.utils import class_logger
from services.models.time_series import TimeSeries


class BlockHeightNotifier(INotified):
    KEY_SERIES_BLOCK_HEIGHT = 'ThorBlockHeight'

    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = class_logger(self)
        self.series = TimeSeries(self.KEY_SERIES_BLOCK_HEIGHT, self.deps.db)

        cfg = self.deps.cfg.last_block
        self.block_height_estimation_interval = cfg.chart.estimation_interval.as_seconds
        self.stuck_alert_time_limit = cfg.stuck_alert.time_limit.as_seconds

        repeat_alert_cooldown_sec = cfg.stuck_alert.repeat_cooldown.as_seconds
        self.repeat_alert_cd = Cooldown(self.deps.db, 'BlockHeightStuckAlert', repeat_alert_cooldown_sec)

    @staticmethod
    def smart_block_time_estimator(points: list, min_period: float):
        results = []
        current_index = len(points) - 1
        while current_index >= 0:
            ts, v = points[current_index]
            back_index = current_index - 1
            while back_index > 0 and ts - points[back_index][0] < min_period:
                back_index -= 1
            if back_index < 0:
                break
            else:
                prev_ts, prev_v = points[back_index]
                dt = ts - prev_ts
                dv = v - prev_v
                results.append((ts, dv / dt))
                current_index = back_index

        results.reverse()
        return results

    async def get_block_time_chart(self, duration_sec=DAY):
        points = await self.series.get_last_values(duration_sec, key='thor_block', with_ts=True)

        if len(points) <= 1:
            return []

        block_rate = self.smart_block_time_estimator(points, self.block_height_estimation_interval)
        return block_rate

    async def get_last_block_time(self) -> Optional[float]:
        chart = await self.get_block_time_chart(self.block_height_estimation_interval * 2)
        if chart:
            return chart[-1][1]
        else:
            return None


    async def on_data(self, sender, data: Dict[str, ThorLastBlock]):
        thor_block = max(v.thorchain for v in data.values()) if data else 0

        if thor_block > 0:
            await self.series.add(thor_block=thor_block)

        # chart = await self.get_block_time_chart()
        # print(f'block time chart = {chart}')
