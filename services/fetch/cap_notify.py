import logging

from aiogram import Bot

from services.config import Config, DB
from localization import LocalizationManager
from services.fetch.model import ThorInfo
from services.broadcast import Broadcaster
from services.fetch.cap import CapInfoFetcher


class CapFetcherNotification(CapInfoFetcher):
    def __init__(self, cfg: Config, broadcaster: Broadcaster, locman: LocalizationManager):
        super().__init__(cfg)
        self.broadcaster = broadcaster
        self.locman = locman
        self.db = broadcaster.db

    async def on_got_info(self, info: ThorInfo):
        if not info.is_ok:
            logging.warning('no info got!')
            return

        old_info = await self.db.get_old_cap()
        await self.db.update_ath(info.price)
        await self.db.set_cap(info)

        if info.cap != old_info.cap:
            await self.notify_when_cap_changed(old_info, info)

    async def notify_when_cap_changed(self, old: ThorInfo, new: ThorInfo):
        async def message_gen(chat_id):
            loc = await self.locman.get_from_db(chat_id, self.db)
            return loc.notification_cap_change_text(old, new)

        users = await self.broadcaster.all_users()
        await self.broadcaster.broadcast(users, message_gen)

