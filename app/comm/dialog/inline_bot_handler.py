import logging
from uuid import uuid4

from aiogram.types import InlineQuery, InputTextMessageContent, InlineQueryResultArticle, InlineQueryResultCachedPhoto

from comm.localization.manager import BaseLocalization
from models.node_info import NetworkNodes
from .base import BaseDialog, inline_bot_handler
from comm.picture.lp_picture import generate_yield_picture
from comm.picture.price_picture import price_graph_from_db
from jobs.runeyield import get_rune_yield_connector
from lib.config import Config
from lib.date_utils import today_str, MINUTE, parse_timespan_to_seconds, DAY
from lib.draw_utils import img_to_bio
from lib.utils import unique_ident
from models.lp_info import LPAddress
from models.net_stats import AlertNetworkStats
from notify.public.best_pool_notify import BestPoolsNotifier
from notify.public.stats_notify import NetworkStatsNotifier


class InlineBotHandlerDialog(BaseDialog):
    DEFAULT_ICON = 'https://raw.githubusercontent.com/thorchain/Resources/master/logos/png/RUNE-ICON-256.png'

    @staticmethod
    def is_enabled(cfg: Config):
        return bool(cfg.get('telegram.inline_bot.enabled', default=True))

    @staticmethod
    def cache_time(cfg: Config):
        return parse_timespan_to_seconds(cfg.as_str('telegram.inline_bot.cache_time', '5m'))

    @inline_bot_handler()
    async def handle(self, inline_query: InlineQuery):
        if not self.is_enabled(self.deps.cfg):
            return

        try:
            text = inline_query.query.strip()
            components = list(map(str.strip, text.split(' ')))
            if not components:
                raise ValueError('invalid command format')

            command = components[0].lower()
            if command == 'pools':
                await self._handle_pools_query(inline_query)
            elif command == 'lp':
                await self._handle_lp_position_query(inline_query, components[1:])
            elif command == 'stats':
                await self._handle_stats_query(inline_query)
            elif command == 'price':
                await self._handle_price_query(inline_query, components)
            else:
                loc = self.get_localization()
                await self._answer_error(inline_query, 'invalid_command',
                                         title=self.loc.INLINE_HINT_HELP_TITLE,
                                         desc=self.loc.INLINE_HINT_HELP_DESC,
                                         text=self.loc.INLINE_HINT_HELP_CONTENT.format(bot=loc.this_bot_name))

        except Exception as e:
            logging.exception('Inline response generation exception')
            await self._answer_internal_error(inline_query, e)

    async def _handle_price_query(self, inline_query: InlineQuery, components):
        if len(components) == 2:
            period = parse_timespan_to_seconds(components[1])
            if period <= MINUTE or period >= 31 * DAY:
                raise ValueError('Period must be >= 1m and =< 31d')
        else:
            period = 3 * DAY
        ident = unique_ident([period], prec='minute')
        graph, graph_name = await price_graph_from_db(self.deps, self.loc, period=period)
        graph_bio = img_to_bio(graph, graph_name)
        await self._answer_photo(inline_query, graph_bio, f'Price of Rune: {period}', ident)

    async def _handle_stats_query(self, inline_query: InlineQuery):
        nsn = NetworkStatsNotifier(self.deps)
        old_info = await nsn.get_previous_stats()
        new_info = self.deps.net_stats

        q_ident = unique_ident([], prec='minute')

        if not new_info.is_ok:
            await self._answer_error(inline_query, q_ident, self.loc.ERROR, self.loc.NOT_READY, self.loc.NOT_READY)
            return

        nodes: NetworkNodes = await self.deps.node_cache.get()

        loc: BaseLocalization = self.get_localization()
        text = loc.notification_text_network_summary(
            AlertNetworkStats(
                old_info, new_info,
                nodes.node_info_list
            )
        )

        await self._answer_results(inline_query, [
            InlineQueryResultArticle(id=q_ident,
                                     title=self.loc.INLINE_STATS_TITLE,
                                     description=self.loc.INLINE_STATS_DESC,
                                     input_message_content=InputTextMessageContent(text))
        ])

    async def _handle_pools_query(self, inline_query: InlineQuery):
        notifier: BestPoolsNotifier = self.deps.best_pools_notifier
        text = self.loc.notification_text_best_pools(notifier.last_pool_detail)

        ident = unique_ident([], prec='minute')
        await self._answer_results(inline_query, [
            InlineQueryResultArticle(id=ident,
                                     title=self.loc.INLINE_TOP_POOLS_TITLE,
                                     description=self.loc.INLINE_TOP_POOLS_DESC,
                                     input_message_content=InputTextMessageContent(text))
        ])

    async def _handle_lp_position_query(self, inline_query: InlineQuery, components: list):
        if len(components) < 2:
            return await self._answer_invalid_query(inline_query)

        address, pool_query, *_ = components

        if not LPAddress.validate_address(address):
            return await self._answer_invalid_address(inline_query)

        ph = await self.deps.pool_cache.get()

        pools_variants = ph.pool_fuzzy_search(pool_query)

        if not pools_variants:
            return await self._answer_pool_not_found(inline_query, pool_query)

        exact_pool = pools_variants[0]

        # GENERATE A REPORT
        rune_yield = get_rune_yield_connector(self.deps)
        lp_report = await rune_yield.generate_yield_report_single_pool(address, exact_pool)
        # todo: idea: make a gallery!
        # summary = await rune_yield.generate_yield_summary(address, pools)

        # GENERATE A PICTURE
        picture = await generate_yield_picture(ph, lp_report, self.loc, value_hidden=False)
        picture_bio = img_to_bio(picture, f'Thorchain_LP_{exact_pool}_{today_str()}.png')

        # UPLOAD AND SEND RESULT
        ident = unique_ident((address, exact_pool), prec='minute')
        loc = self.get_localization()
        title = loc.INLINE_LP_CARD.format(address=address, exact_pool=exact_pool)
        await self._answer_photo(inline_query, picture_bio, title, ident=ident)

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

    async def _answer_internal_error(self, inline_query: InlineQuery, e: Exception):
        loc = self.get_localization()
        await self._answer_error(inline_query, 'internal_error',
                                 title=loc.INLINE_INTERNAL_ERROR_TITLE,
                                 text=loc.INLINE_INTERNAL_ERROR_CONTENT + f' ({e!r})',
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
        ct = self.cache_time(self.deps.cfg)
        await self.deps.telegram_bot.bot.answer_inline_query(inline_query.id, results=items, cache_time=ct)

    async def _answer_photo(self, inline_query, photo, title, ident):
        buffer_chat_id = self.deps.cfg.telegram.buffer_chat
        upload = await self.deps.telegram_bot.bot.send_photo(buffer_chat_id, photo, disable_notification=True)

        original_id = upload.photo[-1].file_id

        ident = ident or str(uuid4())

        await self._answer_results(inline_query, items=[
            InlineQueryResultCachedPhoto(
                id=str(ident),
                title=title,
                photo_file_id=original_id
            )
        ])
