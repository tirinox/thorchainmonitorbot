from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.types import *
from aiogram.utils.helper import HelperMode

from services.lib.texts import kbd
from services.dialog.base import BaseDialog, message_handler


class SettingsStates(StatesGroup):
    mode = HelperMode.snake_case
    MAIN_SETTINGS_MENU = State()
    ASK_LANGUAGE = State()


class SettingsDialog(BaseDialog):
    # ----------- HANDLERS ------------

    async def ask_language(self, message: Message):
        text, kb = self.loc.lang_help()
        await SettingsStates.ASK_LANGUAGE.set()
        await message.answer(text, reply_markup=kb,
                             disable_notification=True)

    @message_handler(state=SettingsStates.ASK_LANGUAGE)
    async def on_asked_language(self, message: Message):
        t = message.text
        if t == self.loc.BUTTON_ENG:
            lang = 'eng'
        elif t == self.loc.BUTTON_RUS:
            lang = 'rus'
        else:
            return False

        self.data['language'] = lang
        self.loc = await self.deps.loc_man.set_lang(message.from_user.id, lang, self.deps.db)
        await self.go_back(message)

    @message_handler(state=SettingsStates.MAIN_SETTINGS_MENU)
    async def on_enter(self, message: Message):
        if message.text == self.loc.BUTTON_SM_BACK_MM:
            await self.go_back(message)
        elif message.text == self.loc.BUTTON_SET_LANGUAGE:
            await self.ask_language(message)
        else:
            await SettingsStates.MAIN_SETTINGS_MENU.set()
            await message.reply(self.loc.TEXT_SETTING_INTRO, reply_markup=kbd(
                [self.loc.BUTTON_SET_LANGUAGE, self.loc.BUTTON_SM_BACK_MM], vert=True
            ))
