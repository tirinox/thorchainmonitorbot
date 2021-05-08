import json
import logging

from localization import BaseLocalization
from services.jobs.fetch.base import INotified
from services.lib.depcont import DepContainer
from services.lib.texts import MessageType
from services.lib.utils import make_stickers_iterator
from services.models.cap_info import ThorCapInfo


class LiquidityCapNotifier(INotified):
    KEY_INFO = 'th_info'

    async def get_old_cap(self):
        try:
            db = self.deps.db
            j = await db.redis.get(self.KEY_INFO)
            return ThorCapInfo.from_json(j)
        except (TypeError, ValueError, AttributeError, json.decoder.JSONDecodeError):
            self.logger.exception('get_old_cap error')
            return ThorCapInfo.error()

    async def save_cap_info(self, cap: ThorCapInfo):
        r = await self.deps.db.get_redis()
        await r.set(self.KEY_INFO, cap.as_json_string)

    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = logging.getLogger(self.__class__.__name__)

        self.raise_stickers = deps.cfg.cap.raised.stickers
        self.raise_sticker_iter = make_stickers_iterator(self.raise_stickers)

    async def on_data(self, sender, data):
        new_info: ThorCapInfo = data
        if not new_info.is_ok:
            self.logger.warning('no info got!')
            return

        old_info = await self.get_old_cap()

        if new_info.is_ok and old_info.is_ok:
            if new_info.price <= 0:
                new_info.price = old_info.price
            await self.save_cap_info(new_info)

            if new_info.cap != old_info.cap:
                await self._notify_when_cap_changed(old_info, new_info)

    async def send_cap_raised_sticker(self):
        sticker = next(self.raise_sticker_iter)
        user_lang_map = self.deps.broadcaster.telegram_chats_from_config(self.deps.loc_man)
        await self.deps.broadcaster.broadcast(user_lang_map.keys(), sticker, message_type=MessageType.STICKER)

    async def _notify_when_cap_changed(self, old: ThorCapInfo, new: ThorCapInfo):
        if new.cap > old.cap:
            await self.send_cap_raised_sticker()

        await self.deps.broadcaster.notify_preconfigured_channels(self.deps.loc_man,
                                                                  BaseLocalization.notification_text_cap_change,
                                                                  old, new)

    async def test(self):
        old_info = await self.get_old_cap()
        await self._notify_when_cap_changed(old_info, old_info)