from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.types import *
from aiogram.utils.helper import HelperMode

from localization.languages import Language
from services.dialog.base import message_handler, DialogWithSettings
from services.dialog.node_op_menu import NodeOpDialog
from services.lib.new_feature import Features
from services.lib.texts import kbd


class SettingsStates(StatesGroup):
    mode = HelperMode.snake_case
    MAIN_SETTINGS_MENU = State()
    ASK_LANGUAGE = State()
    ASK_PRICE_DIV_MIN_PERCENT = State()
    ASK_PRICE_DIV_MAX_PERCENT = State()


class SettingsDialog(DialogWithSettings):
    SETTING_PRICE_DIV_MIN_PERCENT = 'PriceDiv.Min'
    SETTING_PRICE_DIV_MAX_PERCENT = 'PriceDiv.Max'

    # ----------- HANDLERS ------------

    async def ask_language(self, message: Message):
        await SettingsStates.ASK_LANGUAGE.set()

        kb = kbd([self.loc.BUTTON_RUS, self.loc.BUTTON_ENG], one_time=True)
        await message.answer(self.loc.TEXT_SETTINGS_LANGUAGE_SELECT,
                             reply_markup=kb,
                             disable_notification=True)

    @message_handler(state=SettingsStates.ASK_LANGUAGE)
    async def on_asked_language(self, message: Message):
        t = message.text
        if t == self.loc.BUTTON_ENG:
            lang = Language.ENGLISH
        elif t == self.loc.BUTTON_RUS:
            lang = Language.RUSSIAN
        else:
            return False

        await self.update_locale(lang, message)

        await self.go_back(message)

    async def go_to_node_op_settings(self, message: Message):
        await NodeOpDialog(self.loc, self.data, self.deps, self.message).show_main_menu(message)

    def kbd_for_price_div_percent(self, is_min=False, is_max=False):
        options = []
        if is_min:
            options = [0.5, 1, 2, 4]
        elif is_max:
            options = [2, 5, 10, 20]
        return kbd([
            [f'{opt}%' for opt in options],
            [self.loc.BUTTON_BACK, self.loc.BUTTON_PRICE_DIV_NEXT]
        ])

    async def ask_min_price_div_percent(self, message: Message):
        await SettingsStates.ASK_PRICE_DIV_MIN_PERCENT.set()
        await message.answer(
            self.loc.TEXT_PRICE_DIV_MIN_PERCENT, disable_notification=True,
            reply_markup=self.kbd_for_price_div_percent(is_min=True)
        )

    async def try_parse_percent_value(self, message: Message, **kwargs):
        if message.text == self.loc.BUTTON_PRICE_DIV_NEXT:
            return 'next'
        elif message.text == self.loc.BUTTON_BACK:
            return 'back'

        text = message.text.strip('%').strip()
        try:
            value = float(text)
            if value < 0:
                raise ValueError
        except (ValueError, TypeError):
            await message.answer(
                self.loc.TEXT_PRICE_DIV_INVALID_NUMBER, disable_notification=True,
                reply_markup=self.kbd_for_price_div_percent(**kwargs)
            )
        else:
            return value

    @message_handler(state=SettingsStates.ASK_PRICE_DIV_MIN_PERCENT)
    async def handle_min_price_div_percent(self, message: Message):
        value = await self.try_parse_percent_value(message, is_min=True)
        if value == 'back':
            message.text = ''
            await self.on_enter(message)
        elif value == 'next':
            self._settings[self.SETTING_PRICE_DIV_MIN_PERCENT] = None
            await self.ask_max_price_div_percent(message)
        elif value is not None:
            self._settings[self.SETTING_PRICE_DIV_MIN_PERCENT] = value
            await self.ask_max_price_div_percent(message)

    async def ask_max_price_div_percent(self, message: Message):
        await SettingsStates.ASK_PRICE_DIV_MAX_PERCENT.set()
        await message.answer(
            self.loc.TEXT_PRICE_DIV_MAX_PERCENT, disable_notification=True,
            reply_markup=self.kbd_for_price_div_percent(is_max=True)
        )

    @message_handler(state=SettingsStates.ASK_PRICE_DIV_MAX_PERCENT)
    async def handle_max_price_div_percent(self, message: Message):
        value = await self.try_parse_percent_value(message, is_max=True)
        if value == 'back':
            await self.ask_min_price_div_percent(message)
        elif value:
            if value == 'next':
                value = None
            max_percent = self._settings[self.SETTING_PRICE_DIV_MAX_PERCENT] = value
            min_percent = self._settings[self.SETTING_PRICE_DIV_MIN_PERCENT]
            await message.answer(
                self.loc.text_price_div_finish_setup(min_percent=min_percent, max_percent=max_percent),
                disable_notification=True
            )
            message.text = ''
            await self.on_enter(message)

    @message_handler(state=SettingsStates.MAIN_SETTINGS_MENU)
    async def on_enter(self, message: Message):
        button_text_price_divergence = self.text_new_feature(
            self.loc.BUTTON_SET_PRICE_DIVERGENCE,
            Features.F_PERSONAL_PRICE_DIV)

        # Switch options:
        if message.text == self.loc.BUTTON_SM_BACK_MM:
            await self.go_back(message)
        elif message.text == self.loc.BUTTON_SET_LANGUAGE:
            await self.ask_language(message)
        elif message.text == self.loc.BUTTON_SET_NODE_OP_GOTO:
            await self.go_to_node_op_settings(message)
        elif message.text == button_text_price_divergence:
            await self.ask_min_price_div_percent(message)
        else:
            await SettingsStates.MAIN_SETTINGS_MENU.set()
            await message.answer(self.loc.TEXT_SETTING_INTRO, reply_markup=kbd(
                [
                    [self.loc.BUTTON_SET_LANGUAGE, self.loc.BUTTON_SET_NODE_OP_GOTO],
                    [button_text_price_divergence, self.loc.BUTTON_SM_BACK_MM],
                ], vert=True
            ))
