from aiogram.types import *
from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.dispatcher.storage import FSMContextProxy
from aiogram.utils.helper import HelperMode

from localization import LocalizationManager, BaseLocalization
from services.dialog.base import BaseDialog, tg_filters
from services.lib.config import Config
from services.lib.db import DB
from services.models.price import LastPriceHolder
from services.notify.broadcast import Broadcaster


class StakeDialog(BaseDialog):
    class StakeStates(StatesGroup):
        mode = HelperMode.snake_case
        MAIN_MENU = State()
        ADD_ADDRESS = State()

    def __init__(self, cfg: Config, db: DB, loc: BaseLocalization, data: FSMContextProxy,
                 price_holder: LastPriceHolder, broadcaster: Broadcaster):
        super().__init__(cfg, db, loc, data)
        self.price_holder = price_holder
        self.broadcaster = broadcaster

    @tg_filters(state=StakeStates.MAIN_MENU)
    async def on_menu(self, message: Message):
        await message.answer('TEST OK!')
