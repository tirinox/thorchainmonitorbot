from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.types import *
from aiogram.utils.helper import HelperMode

from localization import BaseLocalization
from services.dialog.base import BaseDialog, message_handler
from services.dialog.picture.node_geo_picture import node_geo_pic
from services.dialog.picture.price_picture import price_graph_from_db
from services.dialog.picture.queue_picture import queue_graph
from services.jobs.fetch.fair_price import get_fair_rune_price_cached
from services.jobs.fetch.node_info import NodeInfoFetcher
from services.lib.date_utils import DAY, HOUR, parse_timespan_to_seconds, today_str
from services.lib.draw_utils import img_to_bio
from services.lib.texts import kbd
from services.models.node_info import NodeInfo
from services.models.price import PriceReport
from services.notify.types.cap_notify import LiquidityCapNotifier
from services.notify.types.price_notify import PriceNotifier
from services.notify.types.stats_notify import NetworkStatsNotifier


class MetricsStates(StatesGroup):
    mode = HelperMode.snake_case
    MAIN_METRICS_MENU = State()
    PRICE_SELECT_DURATION = State()
    QUEUE_SELECT_DURATION = State()


class MetricsDialog(BaseDialog):
    # ----------- HANDLERS ------------

    @message_handler(state=MetricsStates.MAIN_METRICS_MENU)
    async def on_enter(self, message: Message):
        if message.text == self.loc.BUTTON_BACK:
            await self.go_back(message)
            return
        elif message.text == self.loc.BUTTON_METR_QUEUE:
            await self.ask_queue_duration(message)
        elif message.text == self.loc.BUTTON_METR_PRICE:
            await self.ask_price_info_duration(message)
        elif message.text == self.loc.BUTTON_METR_CAP:
            await self.show_cap(message)
            await self.show_menu(message)
        elif message.text == self.loc.BUTTON_METR_STATS:
            await self.show_last_stats(message)
            await self.show_menu(message)
        elif message.text == self.loc.BUTTON_METR_NODES:
            await self.show_node_list(message)
            await self.show_menu(message)
        elif message.text == self.loc.BUTTON_METR_LEADERBOARD:
            await self.show_leaderboard(message)
            await self.show_menu(message)
        elif message.text == self.loc.BUTTON_METR_CHAINS:
            await self.show_chain_info(message)
            await self.show_menu(message)
        elif message.text == self.loc.BUTTON_METR_MIMIR:
            await self.show_mimir_info(message)
            await self.show_menu(message)
        else:
            await self.show_menu(message)

    async def show_menu(self, message: Message):
        await MetricsStates.MAIN_METRICS_MENU.set()
        reply_markup = kbd([
            [self.loc.BUTTON_METR_PRICE, self.loc.BUTTON_METR_CAP, self.loc.BUTTON_METR_QUEUE],
            [self.loc.BUTTON_METR_STATS, self.loc.BUTTON_METR_NODES, self.loc.BUTTON_METR_CHAINS],
            [self.loc.BUTTON_METR_LEADERBOARD],
            [self.loc.BUTTON_METR_MIMIR, self.loc.BUTTON_BACK]
        ])
        await message.answer(self.loc.TEXT_METRICS_INTRO,
                             reply_markup=reply_markup,
                             disable_notification=True)

    async def show_cap(self, message: Message):
        info = await LiquidityCapNotifier(self.deps).get_last_cap()
        await message.answer(self.loc.cap_message(info),
                             disable_web_page_preview=True,
                             disable_notification=True)

    async def show_leaderboard(self, message: Message):
        await message.answer(self.loc.text_leaderboard_info(),
                             disable_notification=True,
                             disable_web_page_preview=True)

    async def show_last_stats(self, message: Message):
        nsn = NetworkStatsNotifier(self.deps)
        old_info = await nsn.get_previous_stats()
        new_info = await nsn.get_latest_info()
        loc: BaseLocalization = self.loc
        await message.answer(loc.notification_text_network_summary(old_info, new_info),
                             disable_web_page_preview=True,
                             disable_notification=True)

    async def show_node_list(self, message: Message):
        loading_message = await message.answer(self.loc.LOADING,
                                               disable_notification=True,
                                               disable_web_page_preview=True)

        node_fetcher = NodeInfoFetcher(self.deps)
        result_network_info = await node_fetcher.get_node_list_and_geo_info()  # todo: switch to NodeChurnDetector (DB)
        node_list = result_network_info.node_info_list

        active_node_messages = self.loc.node_list_text(node_list, NodeInfo.ACTIVE)
        standby_node_messages = self.loc.node_list_text(node_list, NodeInfo.STANDBY)
        other_node_messages = self.loc.node_list_text(node_list, 'others')

        await self.safe_delete(loading_message)

        for message_text in (active_node_messages + standby_node_messages + other_node_messages):
            await message.answer(message_text, disable_web_page_preview=True, disable_notification=True)

        pic = await node_geo_pic(result_network_info, self.loc)
        await message.answer_photo(img_to_bio(pic, f'NodeDiversity-{today_str()}.png'), disable_notification=True)

    async def ask_queue_duration(self, message: Message):
        await message.answer(self.loc.TEXT_PRICE_INFO_ASK_DURATION, reply_markup=kbd([
            [
                self.loc.BUTTON_1_HOUR,
                self.loc.BUTTON_24_HOURS,
                self.loc.BUTTON_1_WEEK,
                self.loc.BUTTON_30_DAYS,
            ],
            [
                self.loc.BUTTON_BACK
            ]
        ]))
        await MetricsStates.QUEUE_SELECT_DURATION.set()

    @message_handler(state=MetricsStates.QUEUE_SELECT_DURATION)
    async def on_queue_duration_answered(self, message: Message):
        if message.text == self.loc.BUTTON_1_HOUR:
            period = HOUR
        elif message.text == self.loc.BUTTON_24_HOURS:
            period = DAY
        elif message.text == self.loc.BUTTON_1_WEEK:
            period = 7 * DAY
        elif message.text == self.loc.BUTTON_30_DAYS:
            period = 30 * DAY
        elif message.text == self.loc.BUTTON_BACK:
            message.text = ''
            await self.on_enter(message)
            return
        else:
            period = parse_timespan_to_seconds(message.text.strip())
            if isinstance(period, str):
                await message.answer(f'Error: {period}')
                return
        await self.show_queue(message, period)

    async def show_queue(self, message, period):
        queue_info = self.deps.queue_holder
        plot = await queue_graph(self.deps, self.loc, duration=period)
        await message.answer_photo(plot, caption=self.loc.queue_message(queue_info), disable_notification=True)

    @message_handler(state=MetricsStates.PRICE_SELECT_DURATION)
    async def on_price_duration_answered(self, message: Message):
        if message.text == self.loc.BUTTON_1_HOUR:
            period = HOUR
        elif message.text == self.loc.BUTTON_24_HOURS:
            period = DAY
        elif message.text == self.loc.BUTTON_1_WEEK:
            period = 7 * DAY
        elif message.text == self.loc.BUTTON_30_DAYS:
            period = 30 * DAY
        elif message.text == self.loc.BUTTON_BACK:
            message.text = ''
            await self.on_enter(message)
            return
        else:
            period = parse_timespan_to_seconds(message.text.strip())
            if isinstance(period, str):
                await message.answer(f'Error: {period}')
                return

        fp = await get_fair_rune_price_cached(self.deps.price_holder, self.deps.midgard_connector)
        pn = PriceNotifier(self.deps)
        price_1h, price_24h, price_7d = await pn.historical_get_triplet()
        fp.pool_rune_price = self.deps.price_holder.usd_per_rune
        btc_price = self.deps.price_holder.btc_per_rune

        price_text = self.loc.notification_text_price_update(PriceReport(
            price_1h, price_24h, price_7d,
            market_info=fp,
            btc_pool_rune_price=btc_price),
            halted_chains=self.deps.halted_chains
        )

        graph = await price_graph_from_db(self.deps.db, self.loc, period=period)
        await message.answer_photo(graph)
        await message.answer(price_text,
                             disable_web_page_preview=True,
                             disable_notification=True)

    async def ask_price_info_duration(self, message: Message):
        await message.answer(self.loc.TEXT_PRICE_INFO_ASK_DURATION, reply_markup=kbd([
            [
                self.loc.BUTTON_1_HOUR,
                self.loc.BUTTON_24_HOURS,
                self.loc.BUTTON_1_WEEK,
                self.loc.BUTTON_30_DAYS,
            ],
            [
                self.loc.BUTTON_BACK
            ]
        ]))
        await MetricsStates.PRICE_SELECT_DURATION.set()

    async def show_chain_info(self, message: Message):
        text = self.loc.text_chain_info(list(self.deps.chain_info.values()))
        await message.answer(text,
                             disable_web_page_preview=True,
                             disable_notification=True)

    async def show_mimir_info(self, message: Message):
        texts = self.loc.text_mimir_info(self.deps.mimir_const_holder)
        for text in texts:
            await message.answer(text,
                                 disable_web_page_preview=True,
                                 disable_notification=True)
