import hashlib
import logging
from uuid import uuid4

from aiogram.types import InlineQuery, InputTextMessageContent, InlineQueryResultArticle, InlineQueryResultPhoto, \
    InlineQueryResultCachedPhoto

from localization import BaseLocalization
from services.dialog.base import BaseDialog, inline_bot_handler

# test bot: @thorchain_monitoring_test_bot ADDRESS POOL
from services.dialog.picture.lp_picture import lp_pool_picture
from services.jobs.fetch.runeyield import get_rune_yield_connector
from services.lib.date_utils import today_str
from services.lib.draw_utils import img_to_bio
from services.models.lp_info import LPAddress


class InlineBotHandlerDialog(BaseDialog):
    CACHE_TIME = 5  # sec
    DEFAULT_ICON = 'https://raw.githubusercontent.com/thorchain/Resources/master/logos/png/RUNE-ICON-256.png'

    @inline_bot_handler()
    async def handle(self, inline_query: InlineQuery):
        try:
            text = inline_query.query.strip()

            components = text.split(' ')
            if len(components) < 2:
                raise LookupError('too few query parameters')

            address, pool_query, *_ = components

            if not LPAddress.validate_address(address):
                return await self._answer_invalid_address(inline_query)

            pools_variants = self.deps.price_holder.pool_fuzzy_search(pool_query)

            if not pools_variants:
                return await self._answer_pool_not_found(inline_query, pool_query)

            exact_pool = pools_variants[0]

            # GENERATE A REPORT
            rune_yield = get_rune_yield_connector(self.deps)
            stake_report = await rune_yield.generate_yield_report_single_pool(address, exact_pool)

            # GENERATE A PICTURE
            picture = await lp_pool_picture(stake_report, self.loc, value_hidden=False)
            picture_io = img_to_bio(picture, f'Thorchain_LP_{exact_pool}_{today_str()}.png')

            # UPLOAD AND SEND RESULT
            title = f'LP card of {address} on pool {exact_pool}.'  # todo: loc
            await self._answer_photo(inline_query, picture_io, title)
        except Exception as e:
            logging.exception('Inline response generation exception')
            await self._answer_invalid_query(inline_query)

    def get_localization(self) -> BaseLocalization:
        return self.deps.loc_man.default

    async def _answer_pool_not_found(self, inline_query: InlineQuery, pool):
        loc = self.get_localization()
        await self._answer_error(inline_query, 'pool_not_found',  # todo: loc
                                 title='Pool not found!',  # todo: loc
                                 text=f'"{pool}" no such pool.')  # todo: loc

    async def _answer_invalid_address(self, inline_query: InlineQuery):
        loc = self.get_localization()
        await self._answer_error(inline_query, 'invalid_address',  # todo: loc
                                 title='Invalid address!',  # todo: loc
                                 text='Use THOR or Asset address here.')  # todo: loc

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

    async def _answer_photo(self, inline_query, photo, title):
        buffer_chat_id = self.deps.cfg.telegram.buffer_chat
        upload = await self.deps.bot.send_photo(buffer_chat_id, photo, disable_notification=True)

        # thumb_id = upload.photo[0].file_id
        original_id = upload.photo[-1].file_id

        await self._answer_results(inline_query, items=[
            InlineQueryResultCachedPhoto(
                id=str(uuid4()),
                title=title,
                photo_file_id=original_id
            )
        ])
