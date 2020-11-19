import logging

from localization import LocalizationManager, BaseLocalization
from services.lib.config import Config
from services.lib.db import DB
from services.fetch.base import INotified
from services.models.cap_info import ThorInfo
from services.notify.broadcast import Broadcaster


class CapFetcherNotifier(INotified):
    def __init__(self, cfg: Config, db: DB, broadcaster: Broadcaster, loc_man: LocalizationManager):
        self.logger = logging.getLogger('CapFetcherNotification')
        self.broadcaster = broadcaster
        self.loc_man = loc_man
        self.cfg = cfg
        self.db = db

    async def on_data(self, sender, data):
        new_info: ThorInfo = data
        if not new_info.is_ok:
            self.logger.warning('no info got!')
            return

        old_info = await ThorInfo.get_old_cap(self.db)

        if new_info.is_ok:
            if new_info.price <= 0:
                new_info.price = old_info.price
            await new_info.save(self.db)

            if new_info.cap != old_info.cap:
                await self._notify_when_cap_changed(old_info, new_info)

    async def _notify_when_cap_changed(self, old: ThorInfo, new: ThorInfo):
        await self.broadcaster.notify_preconfigured_channels(self.loc_man,
                                                             BaseLocalization.notification_cap_change_text,
                                                             old, new)
