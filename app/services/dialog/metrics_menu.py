from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.types import *
from aiogram.utils.helper import HelperMode

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


class MetricsDialog(BaseDialog):
    # ----------- HANDLERS ------------

    @message_handler(state=MetricsStates.MAIN_METRICS_MENU)
    async def on_enter(self, message: Message):
        if message.text == self.loc.BUTTON_BACK:
            await self.go_back(message)
            return
        elif message.text == self.loc.BUTTON_METR_QUEUE:
            await self.show_queue(message)
        elif message.text == self.loc.BUTTON_METR_PRICE:
            await self.show_price_info(message)
        elif message.text == self.loc.BUTTON_METR_CAP:
            await self.show_cap(message)

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

    async def show_price_info(self, message: Message):
        fp = await fair_rune_price(self.deps.price_holder)
        pn = PriceNotifier(self.deps)
        price_1h, price_24h, price_7d = await pn.historical_get_triplet()
        fp.real_rune_price = self.deps.price_holder.usd_per_rune
        btc_price = self.deps.price_holder.btc_per_rune

        price_text = self.loc.notification_text_price_update(PriceReport(
            price_1h, price_24h, price_7d,
            fair_price=fp,
            btc_real_rune_price=btc_price))

        await message.answer(price_text,
                             disable_web_page_preview=True,
                             disable_notification=True)
