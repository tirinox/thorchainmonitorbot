import logging

from localization import LocalizationManager
from services.lib.config import Config
from services.lib.db import DB
from services.fetch.base import INotified
from services.models.cap_info import ThorInfo
from services.notify.broadcast import Broadcaster, telegram_chats_from_config


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
        user_lang_map = telegram_chats_from_config(self.cfg, self.loc_man)

        async def message_gen(chat_id):
            return user_lang_map[chat_id].notification_cap_change_text(old, new)

        await self.broadcaster.broadcast(user_lang_map.keys(), message_gen)
