from localization.manager import BaseLocalization
from services.lib.cooldown import Cooldown
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer
from services.lib.utils import class_logger
from services.models.time_series import TimeSeries


class KeyMetricsNotifier(INotified, WithDelegates):
    MAX_POINTS = 10000

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.logger = class_logger(self)

        raw_cd = self.deps.cfg.key_metrics.notification.cooldown
        notify_cd_sec = parse_timespan_to_seconds(raw_cd)
        self.notify_cd = Cooldown(self.deps.db, 'KeyMetrics:Notify', notify_cd_sec)
        self.logger.info(f"it will notify every {notify_cd_sec} sec ({raw_cd})")
        self.series = TimeSeries('KeyMetrics', self.deps.db)

    async def on_data(self, sender, data):
         # self.deps.net_stats = new_info

        # await self.series.add(info=new_info.as_json_string)

        if await self.notify_cd.can_do():
            await self._notify()
            await self.notify_cd.do()

        await self.series.trim_oldest(self.MAX_POINTS)

    async def clear_cd(self):
        await self.notify_cd.clear()

    async def _notify(self):
        await self.deps.broadcaster.notify_preconfigured_channels(
            BaseLocalization.notification_text_key_metrics,
            # todo!
        )
