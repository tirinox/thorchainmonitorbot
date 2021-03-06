import json
import logging

from localization import BaseLocalization
from services.jobs.fetch.base import INotified
from services.lib.depcont import DepContainer
from services.lib.texts import MessageType
from services.lib.utils import make_stickers_iterator
from services.models.cap_info import ThorCapInfo


class LiquidityCapNotifier(INotified):
    KEY_INFO = 'ChaosnetCapInfo'
    KEY_FULL_NOTIFIED = 'Chaosnet:Cap:Full'

    async def get_last_cap(self):
        try:
            db = self.deps.db
            j = await db.redis.get(self.KEY_INFO)
            result = ThorCapInfo.from_json(j)
            return result if result else ThorCapInfo.error()
        except (TypeError, ValueError, AttributeError, json.decoder.JSONDecodeError):
            self.logger.exception('get_old_cap error')
            return ThorCapInfo.error()

    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = logging.getLogger(self.__class__.__name__)

        self.raise_stickers = deps.cfg.cap.raised.stickers
        self.raise_sticker_iter = make_stickers_iterator(self.raise_stickers)

        self.full_notification_enabled = bool(deps.cfg.cap.full.get('enabled', default=True))
        self.full_limit_ratio = float(deps.cfg.cap.full.get('full_limit_ratio', default=0.99))

    async def on_data(self, sender, data):
        new_info: ThorCapInfo = data
        if not new_info.is_ok:
            self.logger.warning('no info got!')
            return

        old_info = await self.get_last_cap()

        if new_info.is_ok:
            if new_info.price <= 0:
                new_info.price = old_info.price

            await self._save_cap_info(new_info)

            if old_info and old_info.is_ok:
                await self._test_cap_raise(new_info, old_info)
                if self.full_notification_enabled:
                    await self._test_cap_limit_is_full(new_info)

    async def _save_cap_info(self, cap: ThorCapInfo):
        r = await self.deps.db.get_redis()
        await r.set(self.KEY_INFO, cap.as_json_string)

    # --- RAISE CAPS ---

    async def _test_cap_raise(self, new: ThorCapInfo, old: ThorCapInfo):
        if new.cap != old.cap:
            if new.cap > old.cap:
                await self.send_cap_raised_sticker()

            await self.deps.broadcaster.notify_preconfigured_channels(self.deps.loc_man,
                                                                      BaseLocalization.notification_text_cap_change,
                                                                      old, new)

            await self._set_cap_limit_reached(False)  # reset full-cap limit notification

    async def send_cap_raised_sticker(self):
        sticker = next(self.raise_sticker_iter)
        user_lang_map = self.deps.broadcaster.telegram_chats_from_config(self.deps.loc_man)
        await self.deps.broadcaster.broadcast(user_lang_map.keys(), sticker, message_type=MessageType.STICKER)

    # --- CAP IS FULL ---

    async def _set_cap_limit_reached(self, is_full):
        await self.deps.db.redis.set(self.KEY_FULL_NOTIFIED, int(is_full))

    async def _get_cap_limit_reached(self):
        db_value = await self.deps.db.redis.get(self.KEY_FULL_NOTIFIED)
        return bool(db_value) and bool(int(db_value))

    async def _test_cap_limit_is_full(self, new_info: ThorCapInfo):
        can_do = not (await self._get_cap_limit_reached())
        if can_do and new_info.pooled_rune >= new_info.cap * self.full_limit_ratio:
            await self.deps.broadcaster.notify_preconfigured_channels(self.deps.loc_man,
                                                                      BaseLocalization.notification_text_cap_full,
                                                                      new_info)
            await self._set_cap_limit_reached(True)
