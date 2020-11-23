from aiogram import Dispatcher, filters
from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.dispatcher.storage import FSMContextProxy
from aiogram.types import *
from aiogram.utils.helper import HelperMode

from localization import LocalizationManager, BaseLocalization
from services.dialog.base import BaseDialog, tg_filters
from services.dialog.stake_info import StakeDialog
from services.fetch.fair_price import fair_rune_price
from services.lib.config import Config
from services.lib.db import DB
from services.models.cap_info import ThorInfo
from services.models.price import PriceReport, LastPriceHolder
from services.notify.broadcast import Broadcaster
from services.notify.types.price_notify import PriceNotifier


class MainMenuDialog(BaseDialog):
    class MainStates(StatesGroup):
        mode = HelperMode.snake_case

        MAIN_MENU = State()
        ASK_LANGUAGE = State()

    def __init__(self, cfg: Config, db: DB, loc: BaseLocalization, data: FSMContextProxy,
                 price_holder: LastPriceHolder, broadcaster: Broadcaster):
        super().__init__(cfg, db, loc, data)
        self.price_holder = price_holder
        self.broadcaster = broadcaster

    @tg_filters(commands='start,lang', state='*')
    async def cmd_start(self, message: Message):
        await self.broadcaster.register_user(message.from_user.id)
        loc_man = LocalizationManager()
        if message.get_command(pure=True) == 'lang' or await loc_man.get_lang(message.from_user.id, self.db) is None:
            # ask language if not set
            await self.MainStates.ASK_LANGUAGE.set()
            text, kb = self.loc.lang_help()
            await message.answer(text, reply_markup=kb,
                                 disable_notification=True)
        else:
            info = await ThorInfo.get_old_cap(self.db)
            await message.answer(self.loc.welcome_message(info),
                                 reply_markup=self.loc.kbd_main_menu())
            await self.MainStates.MAIN_MENU.set()

    @tg_filters(commands='cap', state='*')
    async def cmd_cap(self, message: Message):
        info = await ThorInfo.get_old_cap(self.db)
        await message.answer(self.loc.welcome_message(info),
                             disable_web_page_preview=True,
                             disable_notification=True)

    @tg_filters(commands='price', state='*')
    async def cmd_price(self, message: Message):
        fp = await fair_rune_price()
        pn = PriceNotifier(self.cfg, self.db, self.broadcaster, LocalizationManager())
        price_1h, price_24h, price_7d = await pn.historical_get_triplet()
        fp.real_rune_price = self.price_holder.usd_per_rune

        price_text = self.loc.notification_text_price_update(PriceReport(
            price_1h, price_24h, price_7d,
            fair_price=fp)
        )

        await message.answer(price_text,
                             disable_web_page_preview=True,
                             disable_notification=True)

    @tg_filters(commands='help', state='*')
    async def cmd_help(self, message: Message):
        await message.answer(self.loc.help_message(),
                             disable_web_page_preview=True,
                             disable_notification=True)

    @tg_filters(filters.RegexpCommandsFilter(regexp_commands=[r'/.*']), state='*')
    async def on_unknown_command(self, message: Message):
        await message.answer(self.loc.unknown_command(), disable_notification=True)

    @tg_filters(state=MainStates.ASK_LANGUAGE)
    async def on_lang_set(self, message: Message):
        t = message.text
        if t == self.loc.BUTTON_ENG:
            lang = 'eng'
        elif t == self.loc.BUTTON_RUS:
            lang = 'rus'
        else:
            return False

        self.data['language'] = lang

        await self.MainStates.MAIN_MENU.set()

        self.loc = await LocalizationManager().set_lang(message.from_user.id, lang, self.db)
        await self.cmd_start(message)

    @tg_filters(state=MainStates.MAIN_MENU)
    async def on_main_menu(self, message: Message):
        if message.text == self.loc.BUTTON_MM_PRICE:
            await self.cmd_price(message)
        elif message.text == self.loc.BUTTON_MM_CAP:
            await self.cmd_cap(message)
        elif message.text == self.loc.BUTTON_MM_MY_ADDRESS:
            await StakeDialog(self.cfg, self.db, self.loc, self.data,
                              self.price_holder, self.broadcaster).on_menu(message)
        else:
            return False
