import logging

from localization import BaseLocalization
from services.jobs.fetch.base import INotified
from services.lib.depcont import DepContainer
from services.models.cap_info import ThorCapInfo
from services.models.net_stats import NetworkStats


class NetworkStatsNotifier(INotified):
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = logging.getLogger(self.__class__.__name__)

    async def on_data(self, sender, data):
        d = self.deps
        new_info: NetworkStats = data

        print('NetworkStats: ', new_info)  # todo!

    async def _notify_when_cap_changed(self, old: ThorCapInfo, new: ThorCapInfo):
        pass
        # await self.deps.broadcaster.notify_preconfigured_channels(self.deps.loc_man,
        #                                                       BaseLocalization.notification_text_cap_change,
        #                                                       old, new)
