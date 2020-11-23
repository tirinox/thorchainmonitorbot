from aiogram import Dispatcher
from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.utils.helper import HelperMode

from localization import LocalizationManager
from services.lib.config import Config
from services.lib.db import DB
from services.models.price import LastPriceHolder
from services.notify.broadcast import Broadcaster


class StakeStates(StatesGroup):
    mode = HelperMode.snake_case

    MAIN_MENU = State()
    START = State()
    ASK_LANGUAGE = State()
    DUMMY = State()


def setup_dialog(cfg: Config,
                 dp: Dispatcher,
                 loc_man: LocalizationManager,
                 db: DB,
                 broadcaster: Broadcaster,
                 price_holder: LastPriceHolder):
    ...
    # dp.bot.answer_callback_query()
