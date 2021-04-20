import json
import logging

from localization import BaseLocalization
from services.jobs.fetch.base import INotified
from services.lib.depcont import DepContainer
from services.models.cap_info import ThorCapInfo


class LiquidityCapNotifier(INotified):
    KEY_INFO = 'th_info'

    async def get_old_cap(self):
        try:
            db = self.deps.db
            j = await db.redis.get(self.KEY_INFO)
            return ThorCapInfo.from_json(j)
        except (TypeError, ValueError, AttributeError, json.decoder.JSONDecodeError):
            logging.exception('get_old_cap error')
            return ThorCapInfo.error()

    async def save_cap_info(self, cap: ThorCapInfo):
        r = await self.deps.db.get_redis()
        await r.set(self.KEY_INFO, cap.as_json_string)

    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = logging.getLogger(self.__class__.__name__)

    async def on_data(self, sender, data):
        new_info: ThorCapInfo = data
        if not new_info.is_ok:
            self.logger.warning('no info got!')
            return

        old_info = await self.get_old_cap()

        if new_info.is_ok:
            if new_info.price <= 0:
                new_info.price = old_info.price
            await self.save_cap_info(new_info)

            if new_info.cap != old_info.cap:
                await self._notify_when_cap_changed(old_info, new_info)

    async def _notify_when_cap_changed(self, old: ThorCapInfo, new: ThorCapInfo):
        await self.deps.broadcaster.notify_preconfigured_channels(self.deps.loc_man,
                                                                  BaseLocalization.notification_text_cap_change,
                                                                  old, new)
