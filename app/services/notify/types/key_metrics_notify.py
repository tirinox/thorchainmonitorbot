from datetime import timedelta

from services.jobs.fetch.flipside import FSList
from services.lib.cooldown import Cooldown
from services.lib.date_utils import parse_timespan_to_seconds, DAY, now_ts
from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer
from services.lib.utils import class_logger
from services.models.flipside import FSFees, FSLockedValue, FSSwapCount, FSSwapVolume, KeyStats, KeyStatsDelta
from services.models.time_series import TimeSeries


class KeyMetricsNotifier(INotified, WithDelegates):
    MAX_POINTS = 10000
    MAX_DATA_AGE_DEFAULT = '36h'

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.logger = class_logger(self)

        self.data_max_age = self.deps.cfg.as_interval('key_metrics.data_max_age', self.MAX_DATA_AGE_DEFAULT)

        raw_cd = self.deps.cfg.key_metrics.notification.cooldown
        self.notify_cd_sec = parse_timespan_to_seconds(raw_cd)
        self.notify_cd = Cooldown(self.deps.db, 'KeyMetrics:Notify', self.notify_cd_sec)
        self.logger.info(f"it will notify every {self.notify_cd_sec} sec ({raw_cd})")

        self.series = TimeSeries('KeyMetrics', self.deps.db)

    @property
    def window_in_days(self):
        return int((self.notify_cd_sec + 1) / DAY)

    def is_fresh_enough(self, data: FSList):
        return data and now_ts() - data.latest_date.timestamp() < self.data_max_age

    def convert_to_key_stats(self, data: list) -> KeyStats:
        return KeyStats()


    async def on_data(self, sender, all_data):
        fs_data, prev_pools, current_pools = all_data

        if not prev_pools or not current_pools:
            self.logger.error(f'No pool data! Aborting.')
            return

        fs_data = fs_data.remove_incomplete_rows((FSFees, FSSwapCount, FSLockedValue, FSSwapVolume))

        if not self.is_fresh_enough(fs_data):
            self.logger.error(f'Network data is too old! The most recent date is {fs_data.latest_date}!')
            return

        last_date = fs_data.latest_date
        previous_date = last_date - timedelta(days=self.window_in_days)

        # list of FSxxx objects
        previous_data = fs_data.get(previous_date, [])
        self.logger.info(f'Previous date is {previous_date}; data has {len(previous_data)} entries.')

        # list of FSxxx objects
        current_data = fs_data.most_recent
        self.logger.info(f'Current date is {last_date}; data has {len(current_data)} entries.')

        event = KeyStatsDelta(
            current_data,
            previous_data,
            self.window_in_days
        )

        await self._notify(event)  # fixme: debug. add cool down period1!

        # if await self.notify_cd.can_do():
        #     await self._notify()
        #     await self.notify_cd.do()

        # await self.series.add(info=new_info.as_json_string)
        # await self.series.trim_oldest(self.MAX_POINTS)

    async def clear_cd(self):
        await self.notify_cd.clear()

    async def _notify(self, event):
        await self.pass_data_to_listeners(event)
