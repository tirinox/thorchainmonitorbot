from typing import Dict, Optional

from aiothornode.types import ThorLastBlock

from localization import BaseLocalization
from services.jobs.fetch.base import INotified
from services.lib.cooldown import Cooldown
from services.lib.date_utils import DAY, MINUTE, parse_timespan_to_seconds, now_ts
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
        self.block_height_estimation_interval = parse_timespan_to_seconds(cfg.chart.estimation_interval)
        self.stuck_alert_time_limit = parse_timespan_to_seconds(cfg.stuck_alert.time_limit)

        repeat_alert_cooldown_sec = parse_timespan_to_seconds(cfg.stuck_alert.repeat_cooldown)
        self.stuck_alert_cd = Cooldown(self.deps.db, 'BlockHeightStuckAlert', repeat_alert_cooldown_sec)
        self.last_thor_block = 0
        self.last_thor_block_update_ts = 0

    @staticmethod
    def smart_block_time_estimator(points: list, min_period: float):
        results = []
        current_index = len(points) - 1
        while current_index >= 0:
            ts, v = points[current_index]
            back_index = current_index - 1
            while back_index > 0 and ts - points[back_index][0] < min_period:
                back_index -= 1

            prev_ts, prev_v = points[back_index]
            dt = ts - prev_ts
            if dt >= min_period:
                dv = v - prev_v
                results.append((ts, dv / dt))
                current_index = back_index
            else:
                break

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

    @property
    def time_without_new_blocks(self):
        return now_ts() - self.last_thor_block_update_ts

    async def on_data(self, sender, data: Dict[str, ThorLastBlock]):
        thor_block = max(v.thorchain for v in data.values()) if data else 0

        if thor_block <= 0 or thor_block < self.last_thor_block:
            return

        if self.last_thor_block != thor_block:
            self.last_thor_block_update_ts = now_ts()
            self.last_thor_block = thor_block

        await self.series.add(thor_block=thor_block)

        if self.time_without_new_blocks > self.stuck_alert_time_limit:
            await self._alert_blocks_stuck()

        tm = await self.get_last_block_time()
        print(f'last block time = {tm}')

        # Block time < threshold
        # Block time >= normal

    async def _alert_blocks_stuck(self):
        if await self.stuck_alert_cd.can_do():
            stuck = True
            await self.deps.broadcaster.notify_preconfigured_channels(
                BaseLocalization.notification_text_block_stuck, stuck, self.stuck_alert_time_limit
            )
            await self.stuck_alert_cd.do()
