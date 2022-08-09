from localization.manager import BaseLocalization
from services.lib.delegates import INotified
from services.lib.cooldown import Cooldown
from services.lib.date_utils import DAY, parse_timespan_to_seconds, MINUTE
from services.lib.depcont import DepContainer
from services.lib.utils import class_logger
from services.models.net_stats import NetworkStats
from services.models.price import RuneMarketInfo
from services.models.time_series import TimeSeries


class NetworkStatsNotifier(INotified):
    MAX_POINTS = 10000

    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = class_logger(self)

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

            # fixme: debug
            # old_info = await self._dbg_get_other_info()

            rune_market_info: RuneMarketInfo = await self.deps.rune_market_fetcher.get_rune_market_info()
            await self._notify(old_info, new_info, rune_market_info)
            await self.notify_cd.do()

        await self.series.trim_oldest(self.MAX_POINTS)

    async def clear_cd(self):
        await self.notify_cd.clear()

    async def get_previous_stats(self, ago=DAY):
        tolerance = ago * 0.05 if ago else MINUTE * 2
        start, end = self.series.range_ago(ago, tolerance_sec=tolerance)
        data = await self.series.select(start, end, 1)
        if not data:
            return NetworkStats()
        return NetworkStats.from_json(data[0][1]['info'])

    async def get_latest_info(self):
        info = await self.get_previous_stats(0)
        info.killed_rune_summary = self.deps.killed_rune
        return info

    async def _notify(self, old: NetworkStats, new: NetworkStats, rune_market_info: RuneMarketInfo):
        await self.deps.broadcaster.notify_preconfigured_channels(
            BaseLocalization.notification_text_network_summary,
            old, new, rune_market_info
        )

    async def _dbg_get_other_info(self):
        r = await self.get_previous_stats(0)
        for name, value in r.__dict__.items():
            if isinstance(value, (int, float)):
                r.__dict__[name] += 1
        return r
