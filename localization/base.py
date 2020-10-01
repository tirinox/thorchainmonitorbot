from abc import ABC, abstractmethod

from services.models.cap_info import ThorInfo
from aiogram.types import *


class BaseLocalization(ABC):
    @abstractmethod
    def notification_cap_change_text(self, old: ThorInfo, new: ThorInfo): ...

    @abstractmethod
    def welcome_message(self, info: ThorInfo): ...

    @abstractmethod
    def price_message(self, info: ThorInfo): ...

    BUTTON_RUS = 'Русский'
    BUTTON_ENG = 'English'

    def lang_help(self):
        return (f'Пожалуйста, выберите язык / Please select a language',
                ReplyKeyboardMarkup(keyboard=[[
                    KeyboardButton(self.BUTTON_RUS),
                    KeyboardButton(self.BUTTON_ENG)
                ]], resize_keyboard=True, one_time_keyboard=True))
