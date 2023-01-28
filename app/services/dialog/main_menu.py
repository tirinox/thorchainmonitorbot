from aiogram import filters
from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.types import *
from aiogram.utils.helper import HelperMode

from services.dialog.avatar_picture_dialog import AvatarDialog
from services.dialog.base import message_handler, BaseDialog
from services.dialog.metrics_menu import MetricsDialog
from services.dialog.my_wallets_menu import MyWalletsMenu, LPMenuStates
from services.dialog.node_op_menu import NodeOpDialog
from services.dialog.settings_menu import SettingsDialog
from services.lib.date_utils import DAY
from services.lib.new_feature import Features
from services.lib.texts import kbd
from services.notify.types.cap_notify import LiquidityCapNotifier
from services.notify.user_registry import UserRegistry


class MainStates(StatesGroup):
    mode = HelperMode.snake_case

    MAIN_MENU = State()
    ASK_LANGUAGE = State()
    SETTINGS = State()


class MainMenuDialog(BaseDialog):
    @message_handler(commands='start,lang', state='*')
    async def entry_point(self, message: Message):
        user_id = message.chat.id
        await UserRegistry(self.deps.db).register_user(user_id)
        loc_man = self.deps.loc_man
        current_language = await loc_man.get_lang(user_id, self.deps.db)
        components = message.text.split(' ')
        if len(components) == 2 and components[0] == '/start':
            # deep linking
            await self._handle_start_lp_view(message, components[1])
        elif message.get_command(pure=True) == 'lang' or current_language is None:
            await SettingsDialog(self.loc, self.data, self.deps, self.message).ask_language(message)
        else:
            info = await LiquidityCapNotifier.get_last_cap_from_db(self.deps.db)
            info.price = self.deps.price_holder.usd_per_rune

            keyboard = kbd([
                # 1st row
                [self.my_wallets_button_text, self.loc.BUTTON_MM_METRICS],
                # 2nd row
                [self.loc.BUTTON_MM_MAKE_AVATAR] + (
                    [self.loc.BUTTON_MM_NODE_OP] if NodeOpDialog.is_enabled(self.deps.cfg) else []
                ),
                # 3rd row
                [self.settings_button_text]
            ])

            await message.answer(self.loc.welcome_message(info),
                                 reply_markup=keyboard,
                                 disable_notification=True)
            await MainStates.MAIN_MENU.set()

    @property
    def settings_button_text(self):
        return self.text_new_feature(self.loc.BUTTON_MM_SETTINGS, Features.F_SETTINGS)

    @property
    def my_wallets_button_text(self):
        return self.text_new_feature(self.loc.BUTTON_MM_MY_ADDRESS, Features.F_MY_WALLETS)

    async def _handle_start_lp_view(self, message: Message, address):
        message.text = ''
        await LPMenuStates.MAIN_MENU.set()
        await MyWalletsMenu(self.loc, self.data, self.deps, self.message).show_pool_menu_for_address(
            message, address,
            edit=False,
            external=True)

    @message_handler(commands='cap', state='*')
    async def cmd_cap(self, message: Message):
        await MetricsDialog(self.loc, self.data, self.deps, self.message).show_cap(message)

    @message_handler(commands='price', state='*')
    async def cmd_price(self, message: Message):
        await MetricsDialog(self.loc, self.data, self.deps, self.message).show_price(message, 7 * DAY)

    @message_handler(commands='nodes', state='*')
    async def cmd_nodes(self, message: Message):
        await MetricsDialog(self.loc, self.data, self.deps, self.message).show_node_list(message)

    @message_handler(commands='stats', state='*')
    async def cmd_stats(self, message: Message):
        await MetricsDialog(self.loc, self.data, self.deps, self.message).show_last_stats(message)

    @message_handler(commands='queue', state='*')
    async def cmd_queue(self, message: Message):
        await MetricsDialog(self.loc, self.data, self.deps, self.message).show_queue(message, DAY)

    @message_handler(commands='chains', state='*')
    async def cmd_chains(self, message: Message):
        await MetricsDialog(self.loc, self.data, self.deps, self.message).show_chain_info(message)

    @message_handler(commands='mimir', state='*')
    async def cmd_mimir(self, message: Message):
        await MetricsDialog(self.loc, self.data, self.deps, self.message).show_mimir_info(message)

    @message_handler(commands='cexflow', state='*')
    async def cmd_lp(self, message: Message):
        message.text = ''
        await MetricsDialog(self.loc, self.data, self.deps, self.message).show_cex_flow(message)

    @message_handler(commands='lp', state='*')
    async def cmd_lp(self, message: Message):
        message.text = ''
        await MyWalletsMenu.from_other_dialog(self).call_in_context(MyWalletsMenu.on_enter)

    @message_handler(commands='supply', state='*')
    async def cmd_supply(self, message: Message):
        message.text = ''
        await MetricsDialog(self.loc, self.data, self.deps, self.message).show_rune_supply(message)

    @message_handler(commands='savings', state='*')
    async def cmd_savings(self, message: Message):
        message.text = ''
        await MetricsDialog(self.loc, self.data, self.deps, self.message).show_savers(message)

    @message_handler(commands='voting', state='*')
    async def cmd_voting(self, message: Message):
        message.text = ''
        await MetricsDialog(self.loc, self.data, self.deps, self.message).show_voting_info(message)

    @message_handler(commands='pools', state='*')
    async def cmd_top_pools(self, message: Message):
        message.text = ''
        await MetricsDialog(self.loc, self.data, self.deps, self.message).show_top_pools(message)

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
            await MetricsDialog.from_other_dialog(self).show_main_menu(message)
        elif message.text == self.my_wallets_button_text:
            await MyWalletsMenu.from_other_dialog(self).call_in_context(MyWalletsMenu.on_enter)
        elif message.text == self.settings_button_text:
            await SettingsDialog.from_other_dialog(self).show_main_menu(message)
        elif message.text == self.loc.BUTTON_MM_MAKE_AVATAR:
            await AvatarDialog.from_other_dialog(self).on_enter(message)
        elif message.text == self.loc.BUTTON_MM_NODE_OP and NodeOpDialog.is_enabled(self.deps.cfg):
            await NodeOpDialog.from_other_dialog(self).show_main_menu(message)
        else:
            return False
