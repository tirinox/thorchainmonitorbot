import json
import logging

from localization import LocalizationManager
from services.notify.broadcast import Broadcaster
from services.config import Config
from services.fetch.cap import CapInfoFetcher
from services.models.model import ThorInfo


class CapFetcherNotification(CapInfoFetcher):
    def __init__(self, cfg: Config, broadcaster: Broadcaster, locman: LocalizationManager):
        super().__init__(cfg)
        self.broadcaster = broadcaster
        self.loc_man = locman
        self.db = broadcaster.db

    async def on_got_info(self, info: ThorInfo):
        if not info.is_ok:
            logging.warning('no info got!')
            return

        old_info = await self.get_old_cap()
        await self.update_ath(info.price)
        await self.set_cap(info)

        if info.cap != old_info.cap:
            await self.notify_when_cap_changed(old_info, info)

    async def notify_when_cap_changed(self, old: ThorInfo, new: ThorInfo):
        async def message_gen(chat_id):
            loc = await self.loc_man.get_from_db(chat_id, self.db)
            return loc.notification_cap_change_text(old, new)

        users = await self.broadcaster.all_users()
        await self.broadcaster.broadcast(users, message_gen)

    KEY_INFO = 'th_info'
    KEY_ATH = 'th_ath_rune_price'

    # -- ath --

    async def get_ath(self):
        try:
            ath_str = await self.db.redis.get(self.KEY_ATH)
            return float(ath_str)
        except (TypeError, ValueError, AttributeError):
            return 0.0

    async def update_ath(self, price):
        ath = await self.get_ath()
        if price > ath:
            await self.db.redis.set(self.KEY_ATH, price)
            return True
        return False

    # -- caps --

    async def get_old_cap(self):
        try:
            j = await self.db.redis.get(self.KEY_INFO)
            return ThorInfo.from_json(j)
        except (TypeError, ValueError, AttributeError, json.decoder.JSONDecodeError):
            return ThorInfo.zero()

    async def set_cap(self, info: ThorInfo):
        if self.db.redis:
            await self.db.redis.set(self.KEY_INFO, info.as_json)
