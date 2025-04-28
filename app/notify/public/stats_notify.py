from lib.cooldown import Cooldown
from lib.date_utils import DAY, parse_timespan_to_seconds, MINUTE
from lib.delegates import INotified, WithDelegates
from lib.depcont import DepContainer
from lib.logs import WithLogger
from models.net_stats import NetworkStats, AlertNetworkStats
from models.time_series import TimeSeries


class NetworkStatsNotifier(INotified, WithDelegates, WithLogger):
    MAX_POINTS = 10000

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

        raw_cd = self.deps.cfg.net_summary.notification.cooldown
        notify_cd_sec = parse_timespan_to_seconds(raw_cd)
        self.notify_cd = Cooldown(self.deps.db, 'NetworkStats:Notify', notify_cd_sec)
        self.logger.info(f"it will notify every {notify_cd_sec} sec ({raw_cd})")
        self.series = TimeSeries('NetworkStats', self.deps.db, self.MAX_POINTS)

    async def on_data(self, sender, data):
        new_info: NetworkStats = data
        if not new_info.is_ok:
            return

        self.deps.net_stats = new_info

        await self.series.add(info=new_info.as_json_string)

        if await self.notify_cd.can_do():
            await self.notify_right_now(new_info)
            await self.notify_cd.do()

        # await self.series.trim_oldest(self.MAX_POINTS)

    async def notify_right_now(self, new_info: NetworkStats):
        old_info = await self.get_previous_stats(ago=DAY)  # 24 ago!
        await self.pass_data_to_listeners(AlertNetworkStats(old_info, new_info, self.deps.node_holder.nodes))

    async def clear_cd(self):
        await self.notify_cd.clear()

    async def get_previous_stats(self, ago=DAY):
        tolerance = ago * 0.05 if ago else MINUTE * 10
        start, end = self.series.range_ago(ago, tolerance_sec=tolerance)
        data = await self.series.select(start, end, 1)
        if not data:
            return NetworkStats()
        return NetworkStats.from_json(data[0][1]['info'])

    async def get_latest_info(self):
        return await self.get_previous_stats(0)

    async def _dbg_get_other_info(self):
        r = await self.get_previous_stats(0)
        for name, value in r.__dict__.items():
            if isinstance(value, (int, float)):
                r.__dict__[name] += 1
        return r
