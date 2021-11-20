from typing import Dict, Optional

from aiothornode.types import ThorLastBlock

from localization import BaseLocalization
from services.jobs.fetch.base import INotified
from services.jobs.fetch.last_block import LastBlockFetcher
from services.lib.config import SubConfig
from services.lib.constants import THOR_BLOCK_SPEED
from services.lib.cooldown import Cooldown, CooldownBiTrigger
from services.lib.date_utils import DAY, MINUTE, parse_timespan_to_seconds, now_ts, format_time_ago_short
from services.lib.depcont import DepContainer
from services.lib.utils import class_logger
from services.models.time_series import TimeSeries


class BlockHeightNotifier(INotified):
    KEY_SERIES_BLOCK_HEIGHT = 'ThorBlockHeight'
    KEY_LAST_TIME_BLOCK_UPDATED = 'ThorBlock:LastTime'
    KEY_LAST_TIME_LAST_HEIGHT = 'ThorBlock:LastHeight'
    KEY_BLOCK_SPEED_ALERT_STATE = 'ThorBlock:BlockSpeed:AlertState'

    StateNormal = 'normal'
    StateTooFast = 'fast'
    StateTooSlow = 'slow'

    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = class_logger(self)
        self.series = TimeSeries(self.KEY_SERIES_BLOCK_HEIGHT, self.deps.db)

        cfg: SubConfig = self.deps.cfg.last_block
        self.block_height_estimation_interval = parse_timespan_to_seconds(cfg.chart.estimation_interval)
        self.stuck_alert_time_limit = parse_timespan_to_seconds(cfg.stuck_alert.time_limit)

        self.repeat_stuck_alert_cooldown_sec = parse_timespan_to_seconds(cfg.stuck_alert.repeat_cooldown)
        self.stuck_alert_cd = Cooldown(self.deps.db, 'BlockHeightStuckAlert', self.repeat_stuck_alert_cooldown_sec)
        self.last_thor_block = 0
        self.last_thor_block_update_ts = 0

        self.normal_block_speed = cfg.as_float('normal_block_speed', THOR_BLOCK_SPEED)

        low_speed_dev = 1 + cfg.as_float('low_block_speed_percent', -50) / 100
        self.low_block_speed = self.normal_block_speed * low_speed_dev

        high_speed_dev = 1 + cfg.as_float('high_block_speed_percent', 50) / 100
        self.normal_block_speed = self.normal_block_speed * high_speed_dev

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

    async def get_last_block_height_points(self, duration_sec=DAY):
        return await self.series.get_last_values(duration_sec, key='thor_block', with_ts=True)

    async def get_block_time_chart(self, duration_sec=DAY, convert_to_blocks_per_minute=False):
        points = await self.get_last_block_height_points(duration_sec)

        if len(points) <= 1:
            return []

        block_rate = self.smart_block_time_estimator(points, self.block_height_estimation_interval)
        if convert_to_blocks_per_minute:
            block_rate = [(ts, v * 60) for ts, v in block_rate]
        return block_rate

    async def get_last_block_time(self) -> Optional[float]:
        chart = await self.get_block_time_chart(self.block_height_estimation_interval * 2)
        if chart:
            return chart[-1][1]
        else:
            return None

    async def _get_block_alert_state(self):
        return await self.deps.db.redis.get(self.KEY_BLOCK_SPEED_ALERT_STATE) or self.StateNormal

    async def _set_block_alert_state(self, new_state):
        await self.deps.db.redis.set(self.KEY_BLOCK_SPEED_ALERT_STATE, new_state)

    @property
    def time_without_new_blocks(self):
        return now_ts() - self.last_thor_block_update_ts

    async def _update_block_ts(self, thor_block):
        r = self.deps.db.redis

        if self.last_thor_block_update_ts == 0:
            ts = await r.get(self.KEY_LAST_TIME_BLOCK_UPDATED)
            self.last_thor_block_update_ts = float(ts) if ts else 0
            self.logger.info(f'Loaded last block TS: {format_time_ago_short(self.last_thor_block_update_ts)}')

        if self.last_thor_block == 0:
            block = await r.get(self.KEY_LAST_TIME_LAST_HEIGHT)
            self.last_thor_block = int(block) if block else 0
            self.logger.info(f'Loaded last block height: #{self.last_thor_block}')

        if self.last_thor_block < thor_block:
            self.last_thor_block_update_ts = now_ts()
            self.last_thor_block = thor_block
            await r.set(self.KEY_LAST_TIME_BLOCK_UPDATED, self.last_thor_block_update_ts)
            await r.set(self.KEY_LAST_TIME_LAST_HEIGHT, self.last_thor_block)

    async def on_data(self, sender: LastBlockFetcher, data: Dict[str, ThorLastBlock]):
        thor_block = max(v.thorchain for v in data.values()) if data else 0

        if thor_block <= 0 or thor_block < self.last_thor_block:
            return

        await self._update_block_ts(thor_block)
        await self.series.add(thor_block=thor_block)

        await self._alert_blocks_stuck(sender)

        tm = await self.get_last_block_time()
        print(f'last block time = {tm}')

        # todo: Block time < threshold
        # todo: Block time >= normal

    async def _alert_blocks_stuck(self, fetcher: LastBlockFetcher):
        chart = await self.get_last_block_height_points(self.stuck_alert_time_limit)
        expected_num_of_points = self.stuck_alert_time_limit / fetcher.sleep_period
        if len(chart) < expected_num_of_points * 0.5:
            self.logger.warning(f'Not enough points for THOR block height dynamics evaluation; '
                                f'{expected_num_of_points = }, in fact {len(chart) = } points.')
            return

        first_height = chart[0][1]
        really_stuck = all(first_height == height for _, height in chart[1:])

        self.logger.info(f'Thor Block height {really_stuck = }.')

        cd_trigger = CooldownBiTrigger(self.deps.db, 'BlockHeightStuck', self.repeat_stuck_alert_cooldown_sec,
                                       default=False)
        if await cd_trigger.turn(really_stuck):
            await self.deps.broadcaster.notify_preconfigured_channels(
                BaseLocalization.notification_text_block_stuck, really_stuck, self.time_without_new_blocks
            )
            await self.stuck_alert_cd.do()
