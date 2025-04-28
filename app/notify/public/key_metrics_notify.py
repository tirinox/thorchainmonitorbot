from typing import Optional

from lib.cooldown import Cooldown
from lib.date_utils import parse_timespan_to_seconds, DAY
from lib.delegates import INotified, WithDelegates
from lib.depcont import DepContainer
from lib.logs import WithLogger
from models.key_stats_model import AlertKeyStats
from models.time_series import TimeSeries


class KeyMetricsNotifier(INotified, WithDelegates, WithLogger):
    MAX_POINTS = 10000
    MAX_DATA_AGE_DEFAULT = '36h'

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

        self.data_max_age = self.deps.cfg.as_interval('key_metrics.data_max_age', self.MAX_DATA_AGE_DEFAULT)

        raw_cd = self.deps.cfg.key_metrics.notification.cooldown
        self.notify_cd_sec = parse_timespan_to_seconds(raw_cd)
        self.notify_cd = Cooldown(self.deps.db, 'KeyMetrics:Notify', self.notify_cd_sec)
        self.logger.info(f"it will notify every {self.notify_cd_sec} sec ({raw_cd})")

        self.series = TimeSeries('KeyMetrics', self.deps.db, self.MAX_POINTS)
        self._prev_data: Optional[AlertKeyStats] = None

    @property
    def window_in_days(self):
        return int((self.notify_cd_sec + 1) / DAY)

    async def on_data(self, sender, e: AlertKeyStats):
        if not e.current.pools:
            self.logger.error(f'No pool data! Aborting.')
            return

        if not e.previous.pools:
            self.logger.warning(f'No previous pool data! Go on')

        self._prev_data = e

        if await self.notify_cd.can_do():
            await self._notify(e)
            await self.notify_cd.do()

    @property
    def last_event(self):
        return self._prev_data

    async def clear_cd(self):
        await self.notify_cd.clear()

    async def _notify(self, event):
        await self.pass_data_to_listeners(event)
