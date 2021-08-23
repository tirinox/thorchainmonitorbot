import hashlib
import logging
from uuid import uuid4

from aiogram.types import InlineQuery, InputTextMessageContent, InlineQueryResultArticle, InlineQueryResultCachedPhoto

from localization import BaseLocalization
from services.dialog.base import BaseDialog, inline_bot_handler
# test bot: @thorchain_monitoring_test_bot ADDRESS POOL
from services.dialog.picture.lp_picture import lp_pool_picture
from services.jobs.fetch.runeyield import get_rune_yield_connector
from services.lib.config import Config
from services.lib.date_utils import today_str, MINUTE
from services.lib.draw_utils import img_to_bio
from services.models.lp_info import LPAddress


class InlineBotHandlerDialog(BaseDialog):
    CACHE_TIME = 5 * MINUTE  # sec
    DEFAULT_ICON = 'https://raw.githubusercontent.com/thorchain/Resources/master/logos/png/RUNE-ICON-256.png'

    @staticmethod
    def is_enabled(cfg: Config):
        return bool(cfg.get('telegram.inline_bot.enabled', default=True))

    @inline_bot_handler()
    async def handle(self, inline_query: InlineQuery):
        if not self.is_enabled:
            return

        try:
            text = inline_query.query.strip()

            components = text.split(' ')
            if len(components) < 2:
                return await self._answer_invalid_query(inline_query)

            address, pool_query, *_ = components

            if not LPAddress.validate_address(address):
                return await self._answer_invalid_address(inline_query)

            pools_variants = self.deps.price_holder.pool_fuzzy_search(pool_query)

            if not pools_variants:
                return await self._answer_pool_not_found(inline_query, pool_query)

            exact_pool = pools_variants[0]

            # GENERATE A REPORT
            rune_yield = get_rune_yield_connector(self.deps)
            lp_report = await rune_yield.generate_yield_report_single_pool(address, exact_pool)
            # todo: idea: make a gallery!
            # summary = await rune_yield.generate_yield_summary(address, pools)

            # GENERATE A PICTURE
            picture = await lp_pool_picture(lp_report, self.loc, value_hidden=False)
            picture_io = img_to_bio(picture, f'Thorchain_LP_{exact_pool}_{today_str()}.png')

            # UPLOAD AND SEND RESULT
            ident = hashlib.md5((today_str() + address + exact_pool).encode()).hexdigest()
            loc = self.get_localization()
            title = loc.INLINE_LP_CARD.format(address=address, exact_pool=exact_pool)
            await self._answer_photo(inline_query, picture_io, title, ident=ident)
        except Exception:
            logging.exception('Inline response generation exception')
            await self._answer_internal_error(inline_query)

    def get_localization(self) -> BaseLocalization:
        return self.deps.loc_man.default

    async def _answer_pool_not_found(self, inline_query: InlineQuery, pool):
        loc = self.get_localization()
        await self._answer_error(inline_query, 'pool_not_found',
                                 title=loc.INLINE_POOL_NOT_FOUND_TITLE,
                                 text=loc.INLINE_POOL_NOT_FOUND_TEXT.format(pool=pool))

    async def _answer_invalid_address(self, inline_query: InlineQuery):
        loc = self.get_localization()
        await self._answer_error(inline_query, 'invalid_address',
                                 title=loc.INLINE_INVALID_ADDRESS_TITLE,
                                 text=loc.INLINE_INVALID_ADDRESS_TEXT)

    async def _answer_internal_error(self, inline_query: InlineQuery):
        loc = self.get_localization()
        await self._answer_error(inline_query, 'internal_error',
                                 title=loc.INLINE_INTERNAL_ERROR_TITLE,
                                 text=loc.INLINE_INTERNAL_ERROR_CONTENT,
                                 desc=loc.INLINE_INTERNAL_ERROR_CONTENT)

    async def _answer_invalid_query(self, inline_query: InlineQuery):
        loc = self.get_localization()
        await self._answer_error(inline_query, 'invalid_query',
                                 title=loc.INLINE_INVALID_QUERY_TITLE,
                                 text=loc.INLINE_INVALID_QUERY_CONTENT.format(bot=loc.this_bot_name),
                                 desc=loc.INLINE_INVALID_QUERY_DESC.format(bot=loc.this_bot_name))

    async def _answer_error(self, inline_query: InlineQuery, ident, title, text, desc=None):
        desc = desc or text
        await self._answer_results(inline_query, [
            InlineQueryResultArticle(
                id=ident,
                title=title,
                input_message_content=InputTextMessageContent(text),
                description=desc,
                thumb_url=self.DEFAULT_ICON
            )
        ])

    async def _answer_results(self, inline_query, items):
        await self.deps.bot.answer_inline_query(inline_query.id, results=items, cache_time=self.CACHE_TIME)

    async def _answer_photo(self, inline_query, photo, title, ident):
        buffer_chat_id = self.deps.cfg.telegram.buffer_chat
        upload = await self.deps.bot.send_photo(buffer_chat_id, photo, disable_notification=True)

        original_id = upload.photo[-1].file_id

        ident = ident or str(uuid4())

        await self._answer_results(inline_query, items=[
            InlineQueryResultCachedPhoto(
                id=str(ident),
                title=title,
                photo_file_id=original_id
            )
        ])
