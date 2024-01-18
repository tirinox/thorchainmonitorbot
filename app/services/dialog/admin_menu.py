from typing import Optional

from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.dispatcher.storage import FSMContextProxy
from aiogram.types import Message
from aiogram.utils.helper import HelperMode

from localization.admin import AdminMessages
from localization.eng_base import BaseLocalization
from services.dialog.base import BaseDialog, message_handler
from services.lib.depcont import DepContainer
from services.lib.texts import kbd


class AdminStates(StatesGroup):
    mode = HelperMode.snake_case

    ROOT = State()
    INFO_SUBMENU = State()
    CONTROL_SUBMENU = State()


g_admin_msg: Optional[AdminMessages] = None


class AdminDialog(BaseDialog):
    def __init__(self, loc: BaseLocalization, data: Optional[FSMContextProxy], d: DepContainer, message: Message):
        super().__init__(loc, data, d, message)
        global g_admin_msg
        if not g_admin_msg:
            g_admin_msg = AdminMessages(d)
        self.adm_loc = g_admin_msg

    async def show_main_menu(self, message: Message):
        await AdminStates.ROOT.set()
        reply_markup = kbd([
            [self.adm_loc.BUTT_CONTROL, self.adm_loc.BUTT_INFO],
            [self.adm_loc.BUTT_BACK]
        ])
        await message.answer(self.adm_loc.TEXT_ROOT_INTRO, reply_markup=reply_markup, disable_notification=True)

    @message_handler(state=AdminStates.ROOT)
    async def on_main_menu(self, message: Message):
        if message.text == self.adm_loc.BUTT_BACK:
            await self.go_back(message)
        elif message.text == self.adm_loc.BUTT_INFO:
            await self.show_info_menu(message)
        elif message.text == self.adm_loc.BUTT_CONTROL:
            await self.show_control_menu(message)

    async def show_control_menu(self, message: Message):
        await AdminStates.CONTROL_SUBMENU.set()
        pause_text = (self.adm_loc.BUTT_GLOBAL_RESUME
                      if self.deps.data_controller.all_paused
                      else self.adm_loc.BUTT_GLOBAL_PAUSE)
        await message.answer('Control menu', disable_notification=True, reply_markup=kbd([
            [pause_text],
            [self.adm_loc.BUTT_BACK],
        ]))

    @message_handler(state=AdminStates.CONTROL_SUBMENU)
    async def on_control_menu(self, message: Message):
        if message.text == self.adm_loc.BUTT_BACK:
            await self.show_main_menu(message)
        elif message.text == self.adm_loc.BUTT_GLOBAL_PAUSE:
            await self.require_admin(message)
            self.deps.data_controller.request_global_pause()
            await self.show_control_menu(message)
            await message.reply(self.adm_loc.TEXT_ALL_PAUSED, disable_notification=True)
        elif message.text == self.adm_loc.BUTT_GLOBAL_RESUME:
            await self.require_admin(message)
            self.deps.data_controller.request_global_resume()
            await message.reply(self.adm_loc.TEXT_ALL_RESUMED, disable_notification=True)
            await self.show_control_menu(message)

    async def show_info_menu(self, message: Message):
        await AdminStates.INFO_SUBMENU.set()
        await message.answer('Info menu', disable_notification=True, reply_markup=kbd([
            [self.adm_loc.BUTT_HTTP, self.adm_loc.BUTT_FETCHERS],
            [self.adm_loc.BUTT_SCANNER, self.adm_loc.BUTT_TASKS],
            [self.adm_loc.BUTT_BACK],
        ]))

    @message_handler(state=AdminStates.INFO_SUBMENU)
    async def on_info_menu(self, message: Message):
        if message.text == self.adm_loc.BUTT_BACK:
            await self.show_main_menu(message)
        elif message.text == self.adm_loc.BUTT_HTTP:
            await self.show_debug_info_about_http(message)
        elif message.text == self.adm_loc.BUTT_FETCHERS:
            await self.show_debug_info_fetchers(message)
        elif message.text == self.adm_loc.BUTT_TASKS:
            await self.show_debug_info_tasks(message)
        elif message.text == self.adm_loc.BUTT_SCANNER:
            await self.show_debug_info_scanner(message)

    async def show_debug_info_about_http(self, message: Message):
        text = await self.adm_loc.get_debug_message_text_session()
        await message.answer(text, disable_notification=True, disable_web_page_preview=True)

        text = await self.adm_loc.get_debug_message_text_session(start=10, with_summary=True)
        await message.answer(text,
                             disable_notification=True,
                             disable_web_page_preview=True)

    async def show_debug_info_tasks(self, message: Message):
        text = await self.adm_loc.get_debug_message_tasks()
        await message.answer(text, disable_notification=True, disable_web_page_preview=True)

    async def show_debug_info_fetchers(self, message: Message):
        text = await self.adm_loc.get_debug_message_text_fetcher()
        await message.answer(text,
                             disable_notification=True,
                             disable_web_page_preview=True)

    async def show_debug_info_scanner(self, message: Message):
        text = await self.adm_loc.get_message_about_scanner()
        await message.answer(text,
                             disable_notification=True,
                             disable_web_page_preview=True)
