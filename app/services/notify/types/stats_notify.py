import logging

from localization import BaseLocalization
from services.jobs.fetch.base import INotified
from services.lib.cooldown import Cooldown
from services.lib.date_utils import DAY, parse_timespan_to_seconds, MINUTE
from services.lib.depcont import DepContainer
from services.models.net_stats import NetworkStats
from services.models.time_series import TimeSeries


class NetworkStatsNotifier(INotified):
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = logging.getLogger(self.__class__.__name__)

        raw_cd = self.deps.cfg.net_summary.notification.cooldown
        notify_cd_sec = parse_timespan_to_seconds(raw_cd)
        self.notify_cd = Cooldown(self.deps.db, 'NetworkStats:Notify', notify_cd_sec)
        self.logger.info(f"it will notify every {notify_cd_sec} sec ({raw_cd})")
        self.series = TimeSeries('NetworkStats', self.deps.db)

    async def on_data(self, sender, data):
        new_info: NetworkStats = data
        if not new_info.is_ok:
            return

        await self.series.add(info=new_info.as_json_string)

        if await self.notify_cd.can_do():
            old_info = await self.get_previous_stats(ago=self.notify_cd.cooldown)  # since last time notified
            await self._notify(old_info, new_info)
            await self.notify_cd.do()

    async def clear_cd(self):
        await self.notify_cd.clear()

    async def get_previous_stats(self, ago=DAY):
        tolerance = ago * 0.05 if ago else MINUTE * 2
        start, end = self.series.range_ago(ago, tolerance_sec=tolerance)
        data = await self.series.select(start, end, 1)
        if not data:
            return NetworkStats()
        return NetworkStats.from_json(data[0][1][b'info'])

    async def get_latest_info(self):
        return await self.get_previous_stats(0)

    async def _notify(self, old: NetworkStats, new: NetworkStats):
        await self.deps.broadcaster.notify_preconfigured_channels(
            self.deps.loc_man,
            BaseLocalization.notification_text_network_summary,
            old, new
        )
