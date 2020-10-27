from abc import ABC, abstractmethod

from aiogram.types import *

from services.fetch.price import PoolInfo, RuneFairPrice
from services.models.cap_info import ThorInfo
from services.models.tx import StakeTx, StakePoolStats
from services.utils import format_percent, progressbar


class BaseLocalization(ABC):
    # ----- WELCOME ------

    def _cap_pb(self, info: ThorInfo):
        return f'{progressbar(info.stacked, info.cap, 20)} ({format_percent(info.stacked, info.cap)})\n'

    @abstractmethod
    def help(self): ...

    @abstractmethod
    def welcome_message(self, info: ThorInfo): ...

    BUTTON_RUS = 'Русский'
    BUTTON_ENG = 'English'

    R = 'Rune'

    def lang_help(self):
        return (f'Пожалуйста, выберите язык / Please select a language',
                ReplyKeyboardMarkup(keyboard=[[
                    KeyboardButton(self.BUTTON_RUS),
                    KeyboardButton(self.BUTTON_ENG)
                ]], resize_keyboard=True, one_time_keyboard=True))

    @abstractmethod
    def unknown_command(self): ...

    # ------- CAP -------

    @abstractmethod
    def notification_cap_change_text(self, old: ThorInfo, new: ThorInfo): ...

    @abstractmethod
    def price_message(self, info: ThorInfo, fair_price: RuneFairPrice): ...

    # ------- STAKES -------

    @abstractmethod
    def tx_text(self, tx: StakeTx, rune_per_dollar: float, pool: StakePoolStats, pool_info: PoolInfo): ...

