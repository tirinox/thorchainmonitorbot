from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.types import *
from aiogram.utils.helper import HelperMode

from services.dialog.price_picture import price_graph_from_db
from services.lib.datetime import DAY, HOUR, parse_timespan_to_seconds
from services.lib.plot_graph import img_to_bio
from services.lib.texts import kbd
from services.dialog.base import BaseDialog, message_handler
from services.dialog.queue_picture import queue_graph
from services.fetch.fair_price import fair_rune_price
from services.fetch.queue import QueueFetcher
from services.models.cap_info import ThorInfo
from services.models.price import PriceReport
from services.notify.types.price_notify import PriceNotifier


class MetricsStates(StatesGroup):
    mode = HelperMode.snake_case
    MAIN_METRICS_MENU = State()
    PRICE_SELECT_DURATION = State()


class MetricsDialog(BaseDialog):
    # ----------- HANDLERS ------------

    @message_handler(state=MetricsStates.MAIN_METRICS_MENU)
    async def on_enter(self, message: Message):
        if message.text == self.loc.BUTTON_BACK:
            await self.go_back(message)
            return
        elif message.text == self.loc.BUTTON_METR_QUEUE:
            await self.show_queue(message)
            await self.show_menu(message)
        elif message.text == self.loc.BUTTON_METR_PRICE:
            await self.ask_price_info_duration(message)
        elif message.text == self.loc.BUTTON_METR_CAP:
            await self.show_cap(message)
            await self.show_menu(message)
        else:
            await self.show_menu(message)

    async def show_menu(self, message: Message):
        await MetricsStates.MAIN_METRICS_MENU.set()
        reply_markup = kbd([
            [self.loc.BUTTON_METR_PRICE, self.loc.BUTTON_METR_CAP],
            [self.loc.BUTTON_METR_QUEUE, self.loc.BUTTON_BACK]
        ])
        await message.answer(self.loc.TEXT_METRICS_INTRO,
                             reply_markup=reply_markup,
                             disable_notification=True)

    async def show_cap(self, message: Message):
        info = await ThorInfo.get_old_cap(self.deps.db)
        await message.answer(self.loc.cap_message(info),
                             disable_web_page_preview=True,
                             disable_notification=True)

    async def show_queue(self, message: Message):
        queue_info = self.deps.queue_holder
        plot = await queue_graph(self.deps, self.loc)
        await message.answer_photo(plot, caption=self.loc.queue_message(queue_info), disable_notification=True)

    @message_handler(state=MetricsStates.PRICE_SELECT_DURATION)
    async def on_price_duration_answered(self, message: Message):
        fp = await fair_rune_price(self.deps.price_holder)
        pn = PriceNotifier(self.deps)
        price_1h, price_24h, price_7d = await pn.historical_get_triplet()
        fp.real_rune_price = self.deps.price_holder.usd_per_rune
        btc_price = self.deps.price_holder.btc_per_rune

        price_text = self.loc.notification_text_price_update(PriceReport(
            price_1h, price_24h, price_7d,
            fair_price=fp,
            btc_real_rune_price=btc_price))

        period = HOUR
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
        else:
            period = parse_timespan_to_seconds(message.text.strip())
            if isinstance(period, str):
                await message.answer(f'Error: {period}')
                return

        graph = await price_graph_from_db(self.deps.db, self.loc, period=period)
        await message.answer_photo(graph)
        await message.answer(price_text,
                             disable_web_page_preview=True,
                             disable_notification=True)
        message.text = ''
        await self.on_enter(message)

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
