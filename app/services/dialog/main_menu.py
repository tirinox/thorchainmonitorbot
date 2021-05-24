from aiogram import filters
from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.types import *
from aiogram.utils.helper import HelperMode

from services.dialog.avatar_picture_dialog import AvatarDialog
from services.dialog.base import BaseDialog, message_handler, query_handler
from services.dialog.metrics_menu import MetricsDialog
from services.dialog.settings_menu import SettingsDialog
from services.dialog.lp_info_dialog import LiquidityInfoDialog, LPMenuStates
from services.lib.date_utils import DAY
from services.lib.texts import code
from services.notify.types.cap_notify import LiquidityCapNotifier


class MainStates(StatesGroup):
    mode = HelperMode.snake_case

    MAIN_MENU = State()
    ASK_LANGUAGE = State()
    SETTINGS = State()


class MainMenuDialog(BaseDialog):
    @message_handler(commands='start,lang', state='*')
    async def entry_point(self, message: Message):
        await self.deps.broadcaster.register_user(message.from_user.id)
        loc_man = self.deps.loc_man
        current_language = await loc_man.get_lang(message.from_user.id, self.deps.db)
        components = message.text.split(' ')
        if len(components) == 2 and components[0] == '/start':
            # deep linking
            await self._handle_start_lp_view(message, components[1])
        elif message.get_command(pure=True) == 'lang' or current_language is None:
            await SettingsDialog(self.loc, self.data, self.deps).ask_language(message)
        else:
            info = await LiquidityCapNotifier(self.deps).get_old_cap()

            await message.answer(self.loc.welcome_message(info),
                                 reply_markup=self.loc.kbd_main_menu(),
                                 disable_notification=True)
            await MainStates.MAIN_MENU.set()

    async def _handle_start_lp_view(self, message: Message, address):
        message.text = ''
        await LPMenuStates.MAIN_MENU.set()
        await LiquidityInfoDialog(self.loc, self.data, self.deps).show_pool_menu_for_address(message, address,
                                                                                             edit=False,
                                                                                             external=True)

    @message_handler(commands='cap', state='*')
    async def cmd_cap(self, message: Message):
        await MetricsDialog(self.loc, self.data, self.deps).show_cap(message)

    @message_handler(commands='price', state='*')
    async def cmd_price(self, message: Message):
        message.text = str(DAY)
        await MetricsDialog(self.loc, self.data, self.deps).on_price_duration_answered(message)

    @message_handler(commands='help', state='*')
    async def cmd_help(self, message: Message):
        await message.answer(self.loc.help_message(),
                             disable_web_page_preview=True,
                             disable_notification=True)

    @message_handler(filters.RegexpCommandsFilter(regexp_commands=[r'/.*']), state='*')
    async def on_unknown_command(self, message: Message):
        await message.answer(self.loc.unknown_command(), disable_notification=True)

    @message_handler(state=MainStates.MAIN_MENU)
    async def on_main_menu(self, message: Message):
        if message.text == self.loc.BUTTON_MM_METRICS:
            message.text = ''
            await MetricsDialog(self.loc, self.data, self.deps).on_enter(message)
        elif message.text == self.loc.BUTTON_MM_MY_ADDRESS:
            message.text = ''
            await LiquidityInfoDialog(self.loc, self.data, self.deps).on_enter(message)
        elif message.text == self.loc.BUTTON_MM_SETTINGS:
            message.text = ''
            await SettingsDialog(self.loc, self.data, self.deps).on_enter(message)
        elif message.text == self.loc.BUTTON_MM_MAKE_AVATAR:
            await AvatarDialog(self.loc, self.data, self.deps).on_enter(message)
        elif message.text == self.loc.BUTTON_MM_NODE_OP:
            await message.answer('In development!')  # todo
        else:
            return False
