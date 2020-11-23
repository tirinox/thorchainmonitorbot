from aiogram import Dispatcher, filters
from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.types import *
from aiogram.dispatcher import FSMContext
from aiogram.utils.helper import HelperMode

from localization import LocalizationManager
from services.lib.config import Config
from services.lib.db import DB
from services.fetch.fair_price import fair_rune_price
from services.models.cap_info import ThorInfo
from services.models.price import PriceReport, LastPriceHolder
from services.notify.broadcast import Broadcaster
from services.notify.types.price_notify import PriceNotifier


class MainMenuStates(StatesGroup):
    mode = HelperMode.snake_case

    MAIN_MENU = State()
    START = State()
    ASK_LANGUAGE = State()
    DUMMY = State()


def bootstrap_bot_commands(cfg: Config,
                           dp: Dispatcher,
                           loc_man: LocalizationManager,
                           db: DB,
                           broadcaster: Broadcaster,
                           price_holder: LastPriceHolder):
    @dp.message_handler(commands=['start', 'lang'], state='*')
    async def on_start(message: Message):
        text, kb = loc_man.default.lang_help()
        await MainMenuStates.ASK_LANGUAGE.set()
        await message.answer(text, reply_markup=kb,
                             disable_notification=True)
        await broadcaster.register_user(message.chat.id)

    @dp.message_handler(content_types=ContentType.TEXT, state=MainMenuStates.ASK_LANGUAGE)
    async def on_lang_set(message: Message, state: FSMContext):
        t = message.text
        if t == loc_man.default.BUTTON_ENG:
            lang = 'eng'
        elif t == loc_man.default.BUTTON_RUS:
            lang = 'rus'
        else:
            await on_start(message)
            return

        async with state.proxy() as data:
            data['language'] = lang

        await loc_man.set_lang(message.chat.id, lang, db)
        await send_welcome(message)
        await MainMenuStates.MAIN_MENU.set()

    @dp.message_handler(commands=['cap'], state='*')
    async def send_welcome(message: Message):
        info = await ThorInfo.get_old_cap(db)
        loc = await loc_man.get_from_db(message.chat.id, db)
        welcome_text = loc.welcome_message(info)
        await message.answer(welcome_text, reply_markup=ReplyKeyboardRemove(),
                             disable_web_page_preview=True,
                             disable_notification=True)

    @dp.message_handler(commands=['price'], state='*')
    async def send_price(message: Message):
        loc = await loc_man.get_from_db(message.chat.id, db)
        fp = await fair_rune_price()

        pn = PriceNotifier(cfg, db, broadcaster, loc_man)
        price_1h, price_24h, price_7d = await pn.historical_get_triplet()
        fp.real_rune_price = price_holder.usd_per_rune
        price_text = loc.notification_text_price_update(PriceReport(
            price_1h, price_24h, price_7d,
            fair_price=fp)
        )

        await message.answer(price_text, reply_markup=ReplyKeyboardRemove(),
                             disable_web_page_preview=True,
                             disable_notification=True)

    @dp.message_handler(commands=['help'], state='*')
    async def send_price(message: Message):
        loc = await loc_man.get_from_db(message.chat.id, db)
        await message.answer(loc.help_message(), reply_markup=ReplyKeyboardRemove(),
                             disable_web_page_preview=True,
                             disable_notification=True)

    @dp.message_handler(filters.RegexpCommandsFilter(regexp_commands=[r'/.*']), state='*')
    async def on_unknown_command(message: Message):
        loc = await loc_man.get_from_db(message.chat.id, db)
        await message.answer(loc.unknown_command(), disable_notification=True)
