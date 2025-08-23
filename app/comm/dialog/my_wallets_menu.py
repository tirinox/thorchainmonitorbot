import asyncio
import html
import logging
from contextlib import suppress
from typing import Optional

from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.dispatcher.storage import FSMContextProxy
from aiogram.types import *
from aiogram.utils.helper import HelperMode

from api.aionode.types import ThorSwapperClout
from api.midgard.name_service import add_thor_suffix
from comm.localization.eng_base import BaseLocalization
from comm.picture.lp_picture import generate_yield_picture, lp_address_summary_picture
from comm.telegram.inline_list import TelegramInlineList
from jobs.runeyield import get_rune_yield_connector
from lib.constants import Chains
from lib.date_utils import today_str, parse_timespan_to_seconds
from lib.depcont import DepContainer
from lib.draw_utils import img_to_bio
from lib.money import short_address, short_rune
from lib.new_feature import Features
from lib.texts import kbd
from lib.utils import paste_at_beginning_of_dict, grouper
from models.lp_info import LPAddress
from notify.personal.balance import WalletWatchlist
from notify.personal.bond_provider import BondWatchlist
from notify.personal.helpers import GeneralSettings, Props
from notify.personal.scheduled import PersonalPeriodicNotificationService, PersonalIdTriplet
from .base import message_handler, query_handler, DialogWithSettings
from .message_cat_db import MessageCategoryDB

CAT_ADD_MORE = 'add-more'
CAT_WALLET_MENU = 'wallet-menu'


class LPMenuStates(StatesGroup):
    mode = HelperMode.snake_case
    MAIN_MENU = State()
    WALLET_MENU = State()
    SET_LIMIT = State()
    SET_PERIOD = State()
    WALLET_SETTINGS = State()
    SET_NAME = State()


class MyWalletsMenu(DialogWithSettings):
    QUERY_REMOVE_ADDRESS = 'remove-addr'
    QUERY_SUMMARY_OF_ADDRESS = 'summary-addr'
    QUERY_TOGGLE_VIEW_VALUE = 'toggle-view-value'
    QUERY_TOGGLE_LP_PROT = 'toggle-lp-prot'
    QUERY_TOGGLE_BALANCE = 'toggle-balance'
    QUERY_SET_RUNE_LIMIT = 'set-limit'
    QUERY_CANCEL = 'cancel'
    QUERY_SUBSCRIBE = 'subscribe'
    QUERY_1D = '1d'
    QUERY_7D = '7d'
    QUERY_30D = '30d'
    QUERY_BOND_PROVIDER = 'bond-provider'
    QUERY_WALLET_SETTINGS = 'wallet-settings'
    QUERY_BACK = 'back'
    QUERY_SET_NAME = 'name'
    QUERY_CLEAR_NAME = 'clear-name'

    KEY_CAN_VIEW_VALUE = 'can-view-value'
    KEY_ADD_LP_PROTECTION = 'add-lp-prot'
    KEY_ACTIVE_ADDRESS = 'active-addr'
    KEY_ACTIVE_ADDRESS_INDEX = 'active-addr-id'
    KEY_IS_EXTERNAL = 'is-external'
    KEY_MY_POOLS = 'my-pools'
    KEY_LAST_POOL = 'last-pool'

    MAX_NAME_LEN = 42

    # ----------- ENTER ------------

    @classmethod
    async def easy_enter(cls, source_dialog):
        await cls.from_other_dialog(source_dialog).call_in_context(cls.on_enter)

    async def on_enter(self, message: Message):
        await self._show_address_selection_menu(message)

    # ---- WALLET LIST ------

    async def _add_address_handler(self, message: Message):
        # this handler adds an address
        address = message.text.strip()
        if not address:
            return

        if '|' in address:
            address, name = address.split('|', 1)
            address = address.strip()
            name = name.strip()
        else:
            name = None

        await self.start_typing(message)

        chain = Chains.detect_chain(address) or Chains.BTC

        thor_name = await self.deps.name_service.lookup_thorname_by_name(address.lower(), forced=True)
        if thor_name:
            logging.info(f'Whoa! A user adds THORName "{thor_name.name}"!')
            address = self.deps.name_service.get_thor_address_of_thorname(thor_name)
            chain = Chains.THOR

        if not LPAddress.validate_address(address):
            await message.answer(self.loc.TEXT_INVALID_ADDRESS, disable_notification=True)
            return

        if address.lower() in self.prohibited_addresses:
            await message.answer(self.loc.TEXT_CANNOT_ADD, disable_notification=True)
            return

        await self._add_address(address, chain)

        # If name is not empty, set it
        if name:
            await self.get_name_service(message).set_wallet_local_name(address, name)

        await self.start_typing(message)
        # redraw menu!
        await self._on_selected_address(message, address, 0, edit=False)
        # await self._show_address_selection_menu(message, edit=edit)

    @message_handler(state=LPMenuStates.MAIN_MENU)
    async def wallet_list_message_handler(self, message: Message):
        if message.text == self.loc.BUTTON_BACK:
            await self.go_back(message)
        else:
            await self._add_address_handler(message)

    async def _make_address_keyboard_list(self, my_addresses: dict):
        extra_row = []

        local_ns = self.get_name_service(self.message)

        async def address_label(address):
            # 1) try local name
            name = await local_ns.get_wallet_local_name(address)
            if not name:
                # 2) try THOR name
                name = await self.deps.name_service.lookup_name_by_address(address)
                if name:
                    name = add_thor_suffix(name)

            if not name:
                # 3) just use address if no name
                name = address

            label = short_address(name, 11, 4, filler='..')
            return label, address

        # Every button is tuple of (label, full_address)
        short_addresses = await asyncio.gather(*[address_label(addr) for addr in my_addresses.keys()])

        return TelegramInlineList(
            short_addresses, data_proxy=self.data,
            max_rows=5, back_text=self.loc.BUTTON_BACK, data_prefix='my_addr',
            loc=self.loc
        ).set_extra_buttons_above([extra_row])

    async def _show_address_selection_menu(self, message: Message, edit=False, show_add_more=True):
        await LPMenuStates.MAIN_MENU.set()

        header = self.loc.TEXT_WALLETS_INTRO

        if not edit:
            await self.remove_old_messages(CAT_WALLET_MENU)

        my_addresses = self.my_addresses
        if not my_addresses:
            text = f'{header}\n{self.loc.TEXT_NO_ADDRESSES}'
            await message.answer(text,
                                 reply_markup=kbd([self.loc.BUTTON_BACK]),
                                 disable_notification=True)
        else:
            tg_list = await self._make_address_keyboard_list(my_addresses)
            keyboard = tg_list.keyboard()
            text = f'{header}\n{self.loc.TEXT_YOUR_ADDRESSES}'
            if edit:
                await message.edit_text(text, reply_markup=keyboard)
            else:
                out_message = await message.answer(text, reply_markup=keyboard, disable_notification=True)
                await self.register_message(CAT_WALLET_MENU, out_message)

        if show_add_more and my_addresses:
            msg = self.loc.TEXT_SELECT_ADDRESS_ABOVE if my_addresses else ''
            msg += self.loc.TEXT_SELECT_ADDRESS_SEND_ME
            extra_message = await message.answer(msg, reply_markup=ReplyKeyboardRemove(), disable_notification=True)
            await self.register_message(CAT_ADD_MORE, extra_message)

    async def _on_selected_address(self, message: Message, address, index, edit=True):
        await LPMenuStates.WALLET_MENU.set()
        self.data[self.KEY_ACTIVE_ADDRESS] = address
        self.data[self.KEY_ACTIVE_ADDRESS_INDEX] = index

        await self.show_wallet_menu_for_address(message, address, edit=edit)

    @query_handler(state=LPMenuStates.MAIN_MENU)
    async def on_tap_address(self, query: CallbackQuery):
        keyboard = await self._make_address_keyboard_list(self.my_addresses)
        result = await keyboard.handle_query(query)

        if result.result == result.BACK:
            await self.go_back(query.message)
        elif result.result == result.SELECTED:
            await self._on_selected_address(query.message,
                                            result.selected_data_tag, result.selected_item_index)

    # ----- INSIDE WALLET MENU -----

    @message_handler(state=LPMenuStates.WALLET_MENU)
    async def inside_wallet_message_handler(self, message: Message):
        await self._add_address_handler(message)

    async def show_wallet_menu_for_address(self, message: Message,
                                           address: str,
                                           reload_pools=True,
                                           edit=True,
                                           external=False):
        # external means that it is not in my list! (called from MainMenu)
        self.data[self.KEY_ACTIVE_ADDRESS] = address
        self.data[self.KEY_IS_EXTERNAL] = external

        if reload_pools:
            await self.start_typing(message)

            if edit:
                await message.edit_text(text=self.loc.text_lp_loading_pools(address))

            my_pools = await self._load_my_pools(address)
            self.data[self.KEY_MY_POOLS] = my_pools

        await self._present_wallet_contents_menu(message, edit=edit)

    async def _load_my_pools(self, address: str):
        try:
            rune_yield = get_rune_yield_connector(self.deps)
            pools = await rune_yield.get_my_pools(address)
            pool_names = [p.pool for p in pools]
        except FileNotFoundError:
            logging.error(f'not found pools for address {address}')
            pool_names = []
        return pool_names

    async def _present_wallet_contents_menu(self, message: Message, edit: bool):
        await LPMenuStates.WALLET_MENU.set()

        address = self.current_address
        my_pools = self.my_pools

        address_obj = self._get_address_object(address)
        track_balance = address_obj.get(Props.PROP_TRACK_BALANCE, False)
        min_limit = float(address_obj.get(Props.PROP_MIN_LIMIT, 0))
        chain = Chains.detect_chain(address)

        balances, bond_prov, thor_name, local_name, clout = await asyncio.gather(
            self.get_balances(address, with_trade_accounts=True),
            self.get_bond_provision(address),
            self.deps.name_service.lookup_name_by_address(address),
            self.get_name_service(message).get_wallet_local_name(address),
            self.get_clout(address)
        )

        ph = await self.deps.pool_cache.get()

        text = self.loc.text_inside_my_wallet_title(address, my_pools, balances,
                                                    min_limit if track_balance else None,
                                                    chain, thor_name, local_name,
                                                    clout, bond_prov,
                                                    price_holder=ph)
        inline_kbd = self._keyboard_inside_wallet_menu().keyboard()
        if edit:
            await message.edit_text(text=text,
                                    reply_markup=inline_kbd,
                                    disable_web_page_preview=True)
        else:
            # clean up
            await self.remove_old_messages(CAT_WALLET_MENU)

            # post new menu
            new_msg = await message.answer(text=text,
                                           reply_markup=inline_kbd,
                                           disable_web_page_preview=True,
                                           disable_notification=True)

            # register it
            await self.register_message(CAT_WALLET_MENU, new_msg)

    def _keyboard_inside_wallet_menu(self) -> TelegramInlineList:
        external = self.data.get(self.KEY_IS_EXTERNAL, False)
        my_pools = self.my_pools

        addr_idx = int(self.data.get(self.KEY_ACTIVE_ADDRESS_INDEX, 0))

        # ---------------------------- POOLS ------------------------------
        pool_labels = [(self.loc.label_for_pool_button(pool), pool) for pool in my_pools]

        tg_list = TelegramInlineList(
            pool_labels, data_proxy=self.data,
            max_rows=3,
            back_text='', data_prefix='pools',
            loc=self.loc
        )

        below_button_matrix = []

        # ---------------------------- ROW 1 ------------------------------
        row1 = []

        # No summary button...

        # if my_pools:
        #     # Summary button (only if there are LP pools)
        #     row1.append(InlineKeyboardButton(self.loc.BUTTON_SM_SUMMARY,
        #                                      callback_data=f'{self.QUERY_SUMMARY_OF_ADDRESS}:{addr_idx}'))

        if not external:
            # Wallet settings
            text = self.text_new_feature(self.loc.BUTTON_WALLET_SETTINGS, Features.F_WALLET_SETTINGS)
            row1.append(InlineKeyboardButton(text, callback_data=self.QUERY_WALLET_SETTINGS))

        if row1:
            below_button_matrix.append(row1)

        # ---------------------------- ROW 2 ------------------------------
        # Back button
        row2 = [
            InlineKeyboardButton(self.loc.BUTTON_SM_BACK_TO_LIST, callback_data=tg_list.data_back)
        ]

        if not external:
            # Remove this address button
            row2.append(
                InlineKeyboardButton(
                    self.loc.BUTTON_REMOVE_THIS_ADDRESS,
                    callback_data=f'{self.QUERY_REMOVE_ADDRESS}:{addr_idx}'
                )
            )

        below_button_matrix.append(row2)

        # install all extra buttons to the List
        tg_list.set_extra_buttons_below(below_button_matrix)
        return tg_list

    @query_handler(state=LPMenuStates.WALLET_MENU)
    async def on_wallet_query(self, query: CallbackQuery):
        result = await self._keyboard_inside_wallet_menu().handle_query(query)

        if result.result == result.BACK:
            await self._show_address_selection_menu(query.message, edit=True, show_add_more=False)
        elif result.result == result.SELECTED:
            await self.click_on_wallet_position(query, result.selected_data_tag, allow_subscribe=True)
        elif query.data.startswith(f'{self.QUERY_SUMMARY_OF_ADDRESS}:'):
            await self.view_address_summary(query)
        elif query.data.startswith(f'{self.QUERY_REMOVE_ADDRESS}:'):
            _, index = query.data.split(':')
            await self._remove_address(index)
            await self._show_address_selection_menu(query.message, edit=True, show_add_more=False)
        elif query.data == self.QUERY_WALLET_SETTINGS:
            await self._present_wallet_settings(query.message)
        elif query.data == self.QUERY_SUBSCRIBE:
            await self._toggle_subscription(query)

    async def _show_wallet_again(self, query: CallbackQuery, edit=False):
        address = self.current_address
        await self.show_wallet_menu_for_address(query.message, address, edit=edit)

    # ---- Wallet settings ----

    async def _present_wallet_settings(self, message: Message, edit=True):
        await LPMenuStates.WALLET_SETTINGS.set()
        await self.remove_old_messages(CAT_ADD_MORE)

        my_pools = self.my_pools
        external = self.data.get(self.KEY_IS_EXTERNAL, False)

        address = self.data.get(self.KEY_ACTIVE_ADDRESS)
        address_obj = self._get_address_object(address)
        track_balance = address_obj.get(Props.PROP_TRACK_BALANCE, False)
        track_bond = address_obj.get(Props.PROP_TRACK_BOND, True)
        view_value = self.data.get(self.KEY_CAN_VIEW_VALUE, True)
        chain = Chains.detect_chain(address)
        min_limit = float(address_obj.get(Props.PROP_MIN_LIMIT, 0))
        if not track_balance:
            min_limit = None
        name = await self.get_name_service(message).get_wallet_local_name(address)

        button_matrix = []

        if my_pools:
            # View value ON/OFF toggle switch
            button_matrix.append([InlineKeyboardButton(
                self.loc.BUTTON_VIEW_VALUE_ON if view_value else self.loc.BUTTON_VIEW_VALUE_OFF,
                callback_data=self.QUERY_TOGGLE_VIEW_VALUE)
            ])

        row2 = []
        if chain == Chains.THOR and not external:
            # Track balance ON/OFF toggle switch
            text = self.loc.BUTTON_TRACK_BALANCE_ON if track_balance else self.loc.BUTTON_TRACK_BALANCE_OFF
            text = self.text_new_feature(text, Features.F_PERSONAL_TRACK_BALANCE)
            row2.append(InlineKeyboardButton(text, callback_data=self.QUERY_TOGGLE_BALANCE))

            if track_balance:
                text = self.text_new_feature(self.loc.BUTTON_SET_RUNE_ALERT_LIMIT,
                                             Features.F_PERSONAL_TRACK_BALANCE_LIMIT)
                row2.append(InlineKeyboardButton(text, callback_data=self.QUERY_SET_RUNE_LIMIT))

        if row2:
            button_matrix.append(row2)

        # ---------------------------- ROW 3 ------------------------------

        row3 = []
        if chain == Chains.THOR and not external:
            text = self.loc.BUTTON_TRACK_BOND_ON if track_bond else self.loc.BUTTON_TRACK_BOND_OFF
            text = self.text_new_feature(text, Features.F_BOND_PROVIDER)
            row3.append(InlineKeyboardButton(text, callback_data=self.QUERY_BOND_PROVIDER))

        set_name_text = self.text_new_feature(self.loc.BUTTON_WALLET_NAME, Features.F_WALLET_SETTINGS)
        row3.append(InlineKeyboardButton(set_name_text, callback_data=self.QUERY_SET_NAME))
        button_matrix.append(row3)

        button_matrix.append([
            InlineKeyboardButton(self.loc.BUTTON_BACK, callback_data=self.QUERY_BACK)
        ])

        # ----

        text = self.loc.text_my_wallet_settings(address, name=name, min_limit=min_limit)
        inline_kbd = InlineKeyboardMarkup(inline_keyboard=button_matrix)
        if edit:
            await message.edit_text(text=text,
                                    reply_markup=inline_kbd,
                                    disable_web_page_preview=True)
        else:
            out_message = await message.answer(text=text, reply_markup=inline_kbd, disable_notification=True)
            await self.register_message(CAT_WALLET_MENU, out_message)

    @query_handler(state=LPMenuStates.WALLET_SETTINGS)
    async def on_wallet_settings_query(self, query: CallbackQuery):
        if query.data == self.QUERY_BACK:
            await self._present_wallet_contents_menu(query.message, edit=True)
        elif query.data == self.QUERY_TOGGLE_VIEW_VALUE:
            self.data[self.KEY_CAN_VIEW_VALUE] = not self.data.get(self.KEY_CAN_VIEW_VALUE, True)
            await self._present_wallet_settings(query.message)
        elif query.data == self.QUERY_TOGGLE_BALANCE:
            address = self.current_address
            is_on = self._toggle_address_property(address, Props.PROP_TRACK_BALANCE)
            await self._process_wallet_balance_flag(address, is_on)
            await self._present_wallet_settings(query.message)
        elif query.data == self.QUERY_BOND_PROVIDER:
            address = self.current_address
            is_on = self._toggle_address_property(address, Props.PROP_TRACK_BOND, default=True)
            await self._process_wallet_track_bond_flag(address, is_on)
            await self._present_wallet_settings(query.message)
        elif query.data == self.QUERY_SET_RUNE_LIMIT:
            await self._enter_set_limit(query)
        elif query.data == self.QUERY_SET_NAME:
            await self._enter_wallet_set_name(query)
        await query.answer()

    @query_handler(state=LPMenuStates.SET_PERIOD)
    async def on_period_selected(self, query: CallbackQuery):
        pool = self.data.get(self.KEY_LAST_POOL)
        if not pool:
            return

        await LPMenuStates.WALLET_MENU.set()

        if query.data == self.QUERY_CANCEL:
            period = False
        else:
            period = parse_timespan_to_seconds(query.data)

        if isinstance(period, str):
            return  # error

        address = self.current_address
        user_id = str(self.user_id(query.message))

        try:
            if period:
                alert = self.loc.ALERT_SUBSCRIBED_TO_LP
                text = self.loc.text_subscribed_to_lp(period)

                await self._subscribers.subscribe(PersonalIdTriplet(user_id, address, pool), period)
            else:
                text = ''
                alert = ''

            kb = await self._get_picture_bottom_keyboard(query, address, pool)
            await query.message.edit_reply_markup(reply_markup=kb)

            await query.answer(alert, show_alert=False)
        except Exception as e:
            logging.exception(f'Failed to edit message {e}.')

    # ---- Limit settings

    async def _enter_set_limit(self, query: CallbackQuery):
        await LPMenuStates.SET_LIMIT.set()

        address = self.current_address
        address_obj = self._get_address_object(address)
        current_min_limit = float(address_obj.get(Props.PROP_MIN_LIMIT, 0))

        prefabs = grouper(3, [
            0, 10, 100, 1000,
            5_000, 10_000, 50_000,
            100_000, 500_000
        ])

        def button_title(val):
            if val == 0:
                text = self.loc.TEXT_ANY
            else:
                text = short_rune(val)
            if val == current_min_limit:
                text = '✔️ ' + text
            return text

        buttons = [
            [InlineKeyboardButton(button_title(val), callback_data=val) for val in row]
            for row in prefabs
        ]

        buttons.append([InlineKeyboardButton(self.loc.BUTTON_CANCEL, callback_data=self.QUERY_CANCEL)])
        await query.message.edit_text(self.loc.text_set_rune_limit_threshold(address, current_min_limit),
                                      reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

    @query_handler(state=LPMenuStates.SET_LIMIT)
    async def on_set_limit_query(self, query: CallbackQuery):
        address = self.current_address

        if query.data != self.QUERY_CANCEL:
            self._set_rune_limit(address, query.data)

        await self._present_wallet_settings(query.message)

    @message_handler(state=LPMenuStates.SET_LIMIT)
    async def on_message_set_limit(self, message: Message):
        try:
            value = float(message.text.strip())
        except (ValueError, TypeError):
            await message.reply(self.loc.TEXT_INVALID_LIMIT, disable_notification=True)
            return

        address = self.current_address
        self._set_rune_limit(address, value)

        await self.show_wallet_menu_for_address(message, address, reload_pools=False, edit=False)

    # --- LP Pic generation actions ----

    async def click_on_wallet_position(self, query: CallbackQuery, pool_label, allow_subscribe=False):
        await self.view_pool_report(query, pool_label, allow_subscribe)

    async def view_pool_report(self, query: CallbackQuery, pool, allow_subscribe=False):
        address = self.current_address

        # remember the last pool (if we want to subscribe)
        self.data[self.KEY_LAST_POOL] = pool

        await self.start_typing(query.message)

        # WORK...
        rune_yield = get_rune_yield_connector(self.deps)
        lp_report = await rune_yield.generate_yield_report_single_pool(address, pool)

        # GENERATE A PICTURE
        value_hidden = not self.data.get(self.KEY_CAN_VIEW_VALUE, True)

        ph = await self.deps.pool_cache.get()
        picture = await generate_yield_picture(ph, lp_report, self.loc, value_hidden=value_hidden)
        picture_bio = img_to_bio(picture, f'Thorchain_LP_{pool}_{today_str()}.png')

        # ANSWER
        await self._show_wallet_again(query)

        if allow_subscribe:
            picture_kb = await self._get_picture_bottom_keyboard(query, address, pool)
        else:
            picture_kb = None

        await query.message.answer_photo(picture_bio,
                                         disable_notification=True,
                                         reply_markup=picture_kb)

        # CLEAN UP
        await self.safe_delete(query.message)

    async def view_address_summary(self, query: CallbackQuery):
        address = self.current_address

        my_pools = self.my_pools
        if not my_pools:
            await query.message.answer(self.loc.TEXT_LP_NO_POOLS_FOR_THIS_ADDRESS, disable_notification=True)
            return

        await self.start_typing(query.message)

        # WORK
        rune_yield = get_rune_yield_connector(self.deps)
        yield_summary = await rune_yield.generate_yield_summary(address, my_pools)

        # GENERATE A PICTURE
        value_hidden = not self.data.get(self.KEY_CAN_VIEW_VALUE, True)
        picture = await lp_address_summary_picture(list(yield_summary.reports),
                                                   yield_summary.charts,
                                                   self.loc, value_hidden=value_hidden)
        picture_bio = img_to_bio(picture, f'Thorchain_LP_Summary_{today_str()}.png')

        # ANSWER
        await self._show_wallet_again(query)

        await query.message.answer_photo(picture_bio,
                                         disable_notification=True)

        # CLEAN UP
        await self.safe_delete(query.message)

    # --- MANAGE ADDRESSES ---

    @property
    def my_addresses(self) -> dict:
        return self.global_data.setdefault(Props.KEY_ADDRESSES, {})

    @property
    def my_pools(self):
        return self.data.get(self.KEY_MY_POOLS, []) or []

    @property
    def current_address(self):
        return self.data[self.KEY_ACTIVE_ADDRESS]

    async def _add_address(self, new_addr, chain):
        if not new_addr:
            logging.error('Cannot add empty address!')
            return

        new_addr = str(new_addr).strip()

        address_dict = self.my_addresses
        new_addr_obj = {
            Props.PROP_CHAIN: chain,
            Props.PROP_TRACK_BALANCE: False,
            Props.PROP_MIN_LIMIT: 0,
        }

        # As the dict is ordered, we add new obj at the beginning in a fishy way
        self.global_data[Props.KEY_ADDRESSES] = paste_at_beginning_of_dict(address_dict, new_addr, new_addr_obj)

        # Bond tracker is on by default
        await self._process_wallet_track_bond_flag(new_addr, is_on=True)

    async def _remove_address(self, index):
        try:
            index = int(index)
            address = list(self.my_addresses.keys())[index]
            self.my_addresses.pop(address)
            await self._process_wallet_balance_flag(address, is_on=False)
            await self._process_wallet_track_bond_flag(address, is_on=False)
        except IndexError:
            logging.error(f'Cannot delete address at {index = },')

    def _toggle_address_property(self, address, prop, default=False):
        obj = self._get_address_object(address)
        if obj:
            obj[prop] = not obj.get(prop, default)
            return obj[prop]

    def _set_address_property(self, address, prop, value):
        obj = self._get_address_object(address)
        if obj:
            obj[prop] = value
            return obj[prop]

    def _get_address_object(self, address=None):
        if not address:
            address = self.current_address
        return self.my_addresses.get(address, {})

    def _set_rune_limit(self, address, raw_data):
        try:
            value = float(raw_data)
            self._set_address_property(address, Props.PROP_MIN_LIMIT, value)
        except ValueError:
            logging.error('Failed to parse Rune limit.')
            return

    # --- MISC ---

    async def get_balances(self, address: str, with_trade_accounts=False):
        if LPAddress.is_thor_prefix(address):
            with suppress(Exception):
                balances = await self.deps.trade_acc_fetcher.get_whole_balances(address, with_trade_accounts)
                return balances
            return 'Failed to load balances'

    async def get_bond_provision(self, address: str):
        if LPAddress.is_thor_prefix(address):
            with suppress(Exception):
                nodes = await self.deps.node_cache.get()
                return list(nodes.find_bond_providers(address))
            return 'Failed to load bond provision data'

    async def get_clout(self, address: str) -> Optional[ThorSwapperClout]:
        with suppress(Exception):
            return await self.deps.thor_connector.query_swapper_clout(address)

    async def _process_wallet_balance_flag(self, address: str, is_on: bool):
        user_id = str(self.data.fsm_context.user)
        await self._wallet_watch.set_user_to_node(user_id, address, is_on)

    async def _process_wallet_track_bond_flag(self, address: str, is_on: bool):
        user_id = str(self.data.fsm_context.user)
        await self._bond_provider_watch.set_user_to_node(user_id, address, is_on)

    def __init__(self, loc: BaseLocalization, data: Optional[FSMContextProxy], d: DepContainer, message: Message):
        super().__init__(loc, data, d, message)
        self._wallet_watch = WalletWatchlist(d.db)
        self._bond_provider_watch = BondWatchlist(d.db)
        self._subscribers = PersonalPeriodicNotificationService(d)

        prohibited_addresses = self.deps.cfg.get_pure('native_scanner.prohibited_addresses')
        self.prohibited_addresses = prohibited_addresses if isinstance(prohibited_addresses, list) else []

        self.dbg_fast_subscription = self.deps.cfg.get_pure('telegram.debug', False)

    async def _toggle_subscription(self, query: CallbackQuery):
        pool = self.data.get(self.KEY_LAST_POOL)
        if not pool:
            return

        address = self.current_address
        user_id = str(self.user_id(query.message))
        tr = PersonalIdTriplet(user_id, address, pool)

        is_subscribed = await self._is_subscribed(tr)
        if is_subscribed:
            await self._subscribers.unsubscribe(tr)
            kb = await self._get_picture_bottom_keyboard(query, address, pool)
            await query.message.edit_reply_markup(reply_markup=kb)
            await query.answer(self.loc.ALERT_UNSUBSCRIBED_FROM_LP)
        else:
            await LPMenuStates.SET_PERIOD.set()
            keyboard = [
                [
                    InlineKeyboardButton(self.loc.BUTTON_LP_PERIOD_1D, callback_data='1d'),
                    InlineKeyboardButton(self.loc.BUTTON_LP_PERIOD_1W, callback_data='7d'),
                    InlineKeyboardButton(self.loc.BUTTON_LP_PERIOD_1M, callback_data='30d'),
                ],
                [
                    InlineKeyboardButton(self.loc.BUTTON_CANCEL, callback_data=self.QUERY_CANCEL),
                ]
            ]

            if self.deps.cfg.is_debug_mode:
                keyboard.insert(1, [
                    InlineKeyboardButton('Debug: 30s', callback_data='30'),
                ])

            kb = InlineKeyboardMarkup(inline_keyboard=keyboard)

            if self.dbg_fast_subscription:
                kb.inline_keyboard[0].append(InlineKeyboardButton("Dbg: 30 sec", callback_data='30'))

            await query.message.edit_reply_markup(kb)
            await query.answer()

    async def _is_subscribed(self, tr: PersonalIdTriplet):
        return await self._subscribers.when_next(tr) is not None

    async def _get_picture_bottom_keyboard(self, query: CallbackQuery, address, pool):
        user_id = str(self.user_id(query.message))

        is_subscribed = await self._is_subscribed(PersonalIdTriplet(user_id, address, pool))
        picture_kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    self.loc.BUTTON_LP_UNSUBSCRIBE if is_subscribed else self.loc.BUTTON_LP_SUBSCRIBE,
                    callback_data=self.QUERY_SUBSCRIBE
                )
            ],
        ])
        return picture_kb

    # --- Set name ---

    @message_handler(state=LPMenuStates.SET_NAME)
    async def set_name_message_handler(self, message: Message):
        name = message.text.strip()[:self.MAX_NAME_LEN]
        name = html.escape(name)

        await self.get_name_service(message).set_wallet_local_name(self.current_address, name)
        await self._present_wallet_settings(message, edit=False)

    @query_handler(state=LPMenuStates.SET_NAME)
    async def on_set_name_query(self, query: CallbackQuery):
        if query.data == self.QUERY_CANCEL:
            pass
        elif query.data == self.QUERY_CLEAR_NAME:
            await self.get_name_service(query.message).delete_wallet_local_name(self.current_address)
            await query.answer(self.loc.TEXT_NAME_UNSET)

        await self._present_wallet_settings(query.message, edit=True)

    async def _enter_wallet_set_name(self, query: CallbackQuery):
        await LPMenuStates.SET_NAME.set()

        address = self.current_address
        button_matrix = []

        name = await self.get_name_service(query.message).get_wallet_local_name(address)
        if name:
            button_matrix.append([
                InlineKeyboardButton(self.loc.BUTTON_CLEAR_NAME, callback_data=self.QUERY_CLEAR_NAME)
            ])

        button_matrix.append([InlineKeyboardButton(self.loc.BUTTON_CANCEL, callback_data=self.QUERY_CANCEL)])

        await query.message.edit_text(
            self.loc.text_wallet_name_dialog(address, name),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=button_matrix)
        )

    # ---- Utils ----

    def get_name_service(self, message):
        return self.deps.name_service.get_local_service(self.user_id(message))

    def get_message_tracker(self, message, category: str):
        return MessageCategoryDB(self.deps.db, self.user_id(message), category)

    @property
    def global_data(self):
        """ This uses "settings" instead of Telegram context """
        return self.settings.setdefault(GeneralSettings.BALANCE_TRACK, {})

    async def remove_old_messages(self, category):
        with suppress(Exception):
            await self.get_message_tracker(self.message, category).delete_all(self.deps.telegram_bot)

    async def register_message(self, category, message: Message):
        with suppress(Exception):
            await self.get_message_tracker(message, category).push(message.message_id)
