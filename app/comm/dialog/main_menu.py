from typing import Optional

from aiogram import filters
from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.dispatcher.storage import FSMContextProxy
from aiogram.types import *
from aiogram.utils.helper import HelperMode

from comm.localization.eng_base import BaseLocalization
from lib.date_utils import DAY
from lib.depcont import DepContainer
from lib.new_feature import Features
from lib.texts import kbd
from notify.personal.scheduled import PersonalPeriodicNotificationService
from notify.public.cap_notify import LiquidityCapNotifier
from notify.user_registry import UserRegistry
from .admin_menu import AdminDialog
from .avatar_picture_dialog import AvatarDialog
from .base import message_handler, BaseDialog
from .metrics_menu import MetricsDialog
from .my_wallets_menu import MyWalletsMenu, LPMenuStates
from .node_op_menu import NodeOpDialog
from .settings_menu import SettingsDialog


class MainStates(StatesGroup):
    mode = HelperMode.snake_case

    MAIN_MENU = State()
    ASK_LANGUAGE = State()
    SETTINGS = State()


class MainMenuDialog(BaseDialog):
    def __init__(self, loc: BaseLocalization, data: Optional[FSMContextProxy], d: DepContainer, message: Message):
        super().__init__(loc, data, d, message)

    @message_handler(commands='start,lang', state='*')
    async def entry_point(self, message: Message):
        user_id = self.user_id(message)
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
        await MyWalletsMenu.from_other_dialog(self).show_wallet_menu_for_address(
            message, address,
            edit=False,
            external=True
        )

    # @message_handler(commands='cap', state='*')
    # async def cmd_cap(self, message: Message):
    #     await self.build_metrics_dialog().show_cap(message)

    @message_handler(commands='price', state='*')
    async def cmd_price(self, message: Message):
        await self.build_metrics_dialog().show_price(message, 7 * DAY)

    @message_handler(commands='nodes', state='*')
    async def cmd_nodes(self, message: Message):
        await self.build_metrics_dialog().show_node_list(message)

    @message_handler(commands='stats', state='*')
    async def cmd_stats(self, message: Message):
        await self.build_metrics_dialog().show_last_stats(message)

    @message_handler(commands='queue', state='*')
    async def cmd_queue(self, message: Message):
        await self.build_metrics_dialog().show_queue(message, DAY)

    @message_handler(commands='chains', state='*')
    async def cmd_chains(self, message: Message):
        await self.build_metrics_dialog().show_chain_info(message)

    @message_handler(commands='mimir', state='*')
    async def cmd_mimir(self, message: Message):
        await self.build_metrics_dialog().show_mimir_info(message)

    @message_handler(commands='cexflow', state='*')
    async def cmd_cex_flow(self, message: Message):
        message.text = ''
        await self.build_metrics_dialog().show_cex_flow(message)

    @message_handler(commands='lp', state='*')
    async def cmd_lp(self, message: Message):
        message.text = ''
        await MyWalletsMenu.easy_enter(self)

    @message_handler(commands='wallets', state='*')
    async def cmd_wallets(self, message: Message):
        message.text = ''
        await MyWalletsMenu.easy_enter(self)

    @message_handler(commands='supply', state='*')
    async def cmd_supply(self, message: Message):
        message.text = ''
        await self.build_metrics_dialog().show_rune_supply(message)

    @message_handler(commands='voting', state='*')
    async def cmd_voting(self, message: Message):
        message.text = ''
        await self.build_metrics_dialog().show_voting_info(message)

    @message_handler(commands='pools', state='*')
    async def cmd_top_pools(self, message: Message):
        message.text = ''
        await self.build_metrics_dialog().show_top_pools(message)

    @message_handler(commands='pol', state='*')
    async def cmd_pol(self, message: Message):
        message.text = ''
        await self.build_metrics_dialog().show_pol_state(message)

    @message_handler(commands='help', state='*')
    async def cmd_help(self, message: Message):
        await message.answer(self.loc.help_message(),
                             disable_web_page_preview=True,
                             disable_notification=True)

    @message_handler(commands='debug', state='*')
    async def cmd_debug(self, message: Message):
        await self.require_admin(message)
        await AdminDialog.from_other_dialog(self).show_main_menu(message)

    @message_handler(commands='weekly', state='*')
    async def cmd_weekly(self, message: Message):
        await self.build_metrics_dialog().show_weekly_stats(message)

    @message_handler(commands='tradeacc', state='*')
    async def cmd_trade_acc_stats(self, message: Message):
        await self.build_metrics_dialog().show_trade_acc_stats(message)

    @message_handler(commands='burntrune,burnedrune,burn', state='*')
    async def cmd_rune_burn(self, message: Message):
        await self.build_metrics_dialog().show_rune_burned(message)

    @message_handler(commands='rujimerge', state='*')
    async def cmd_ruji_merge(self, message: Message):
        await self.build_metrics_dialog().show_rujira_merge_stats(message)

    @message_handler(commands='secured', state='*')
    async def cmd_secured_assets(self, message: Message):
        await self.build_metrics_dialog().show_secured_assets_stats(message)

    @message_handler(filters.RegexpCommandsFilter(regexp_commands=[r'^/unsub_.*']), state='*')
    async def on_unsubscribe_command(self, message: Message):
        # Commands like /unsub_sMth1
        unsub_id = message.text.split('_')[1]
        is_good = await PersonalPeriodicNotificationService(self.deps).unsubscribe_by_id(unsub_id)
        text = self.loc.ALERT_UNSUBSCRIBED_FROM_LP if is_good else self.loc.ALERT_UNSUBSCRIBE_FAILED
        await message.answer(text, disable_notification=True)

    @message_handler(filters.RegexpCommandsFilter(regexp_commands=[r'/.*']), state='*')
    async def on_unknown_command(self, message: Message):
        await message.answer(self.loc.unknown_command(), disable_notification=True)

    @message_handler(state=MainStates.MAIN_MENU)
    async def on_main_menu(self, message: Message):
        if message.text == self.loc.BUTTON_MM_METRICS:
            await self.build_metrics_dialog().show_main_menu(message)
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

    def build_metrics_dialog(self):
        return MetricsDialog.from_other_dialog(self)
