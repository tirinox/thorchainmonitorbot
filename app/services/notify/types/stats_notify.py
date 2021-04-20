import logging

from aioredis import Redis

from localization import BaseLocalization
from services.jobs.fetch.base import INotified
from services.lib.cooldown import Cooldown
from services.lib.date_utils import DAY, parse_timespan_to_seconds
from services.lib.depcont import DepContainer
from services.models.net_stats import NetworkStats


class NetworkStatsNotifier(INotified):
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = logging.getLogger(self.__class__.__name__)
        self.save_every_day_cd = Cooldown(self.deps.db, 'NetworkStats:EveryDay', DAY)

        notify_cd_sec = parse_timespan_to_seconds(self.deps.cfg.net_summary.notification.cooldown)
        self.notify_cd = Cooldown(self.deps.db, 'NetworkStats:Notify', notify_cd_sec)
        self.logger.info(f"it will notify every {notify_cd_sec} sec")

    async def on_data(self, sender, data):
        new_info: NetworkStats = data
        if not new_info.is_ok:
            return

        # update info every day
        if await self.save_every_day_cd.can_do():
            await self._save_stats(new_info)
            await self.save_every_day_cd.do()

        if await self.notify_cd.can_do():
            old_info = await self._load_saved_stats()
            await self._notify(new_info, old_info)
            await self.notify_cd.do()

    async def clear_cd(self):
        await self.notify_cd.clear()
        await self.save_every_day_cd.clear()

    DB_KEY_PREV_NETWORK_STATS = 'NetworkStats:Previous'

    async def _save_stats(self, stats: NetworkStats):
        r: Redis = await self.deps.db.get_redis()
        await r.set(self.DB_KEY_PREV_NETWORK_STATS, stats.as_json_string)

    async def _load_saved_stats(self):
        r: Redis = await self.deps.db.get_redis()
        data = await r.get(self.DB_KEY_PREV_NETWORK_STATS)
        stats = NetworkStats.from_json(data)
        return stats if stats else NetworkStats()

    async def _notify(self, old: NetworkStats, new: NetworkStats):
        await self.deps.broadcaster.notify_preconfigured_channels(
            self.deps.loc_man,
            BaseLocalization.notification_text_network_summary,
            old, new
        )
