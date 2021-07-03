import asyncio
import logging
from dataclasses import asdict

from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.types import *
from aiogram.utils.exceptions import MessageToDeleteNotFound
from aiogram.utils.helper import HelperMode

from services.dialog.base import BaseDialog, message_handler, query_handler
from services.dialog.picture.lp_picture import lp_pool_picture, lp_address_summary_picture
from services.jobs.fetch.runeyield import get_rune_yield_connector
from services.lib.constants import NetworkIdents, Chains
from services.lib.date_utils import today_str
from services.lib.draw_utils import img_to_bio
from services.lib.money import short_address
from services.lib.texts import code, grouper, kbd, cut_long_text
from services.models.lp_info import LPAddress


def get_runeyield_info_address(network: str, address: str, chain: str = Chains.THOR):
    if network == NetworkIdents.CHAOSNET_BEP2CHAIN:
        return f'https://runestake.info/debug?address={address}'
    elif network == NetworkIdents.TESTNET_MULTICHAIN:
        return f'https://mctn.vercel.app/dashboard?thor={address}'  # todo thor address only?
    else:
        chain = chain.lower()
        return f'https://app.runeyield.info/dashboard?{chain}={address}'  # todo


class LPMenuStates(StatesGroup):
    mode = HelperMode.snake_case
    MAIN_MENU = State()


class LiquidityInfoDialog(BaseDialog):
    QUERY_VIEW_ADDRESS = 'view-addr'
    QUERY_REMOVE_ADDRESS = 'remove-addr'
    QUERY_SUMMARY_OF_ADDRESS = 'summary-addr'
    QUERY_BACK_TO_ADDRESS_LIST = 'back-to-addr-list'
    QUERY_BACK_TOGGLE_VIEW_VALUE = 'toggle-view-value'
    QUERY_VIEW_POOL = 'view-pool'

    KEY_MY_ADDRESSES = 'my-address-list'
    KEY_CAN_VIEW_VALUE = 'can-view-value'
    KEY_ACTIVE_ADDRESS = 'active-addr'
    KEY_IS_EXTERNAL = 'is-external'
    KEY_ACTIVE_ADDRESS_INDEX = 'active-addr-id'
    KEY_MY_POOLS = 'my-pools'

    @property
    def my_addresses(self):
        raw = self.data.get(self.KEY_MY_ADDRESSES, [])
        return [LPAddress(**j) for j in raw]

    def add_address(self, new_addr, chain=Chains.BNB):
        new_addr = str(new_addr).strip()
        current_list = self.my_addresses
        my_unique_addr = set((a.chain, a.address) for a in current_list)
        if (chain, new_addr) not in my_unique_addr:
            self.data[self.KEY_MY_ADDRESSES] = [asdict(a) for a in current_list + [LPAddress(new_addr)]]

    def remove_address(self, index):
        del self.data[self.KEY_MY_ADDRESSES][int(index)]

    def kbd_for_addresses(self):
        buttons = []
        for i, addr in enumerate(self.my_addresses):
            data = f'{self.QUERY_VIEW_ADDRESS}:{i}'
            buttons.append(InlineKeyboardButton(short_address(addr.address, begin=10, end=7), callback_data=data))
        return InlineKeyboardMarkup(inline_keyboard=grouper(2, buttons))

    async def display_addresses(self, message: Message, edit=False):
        addresses = self.my_addresses
        if not addresses:
            await message.answer(self.loc.TEXT_NO_ADDRESSES,
                                 reply_markup=kbd([self.loc.BUTTON_BACK]),
                                 disable_notification=True)
        else:
            if edit:
                await message.edit_text(self.loc.TEXT_YOUR_ADDRESSES, reply_markup=self.kbd_for_addresses())
            else:
                await message.answer(self.loc.TEXT_YOUR_ADDRESSES, reply_markup=self.kbd_for_addresses())

    def kbd_for_pools(self):
        external = self.data.get(self.KEY_IS_EXTERNAL, False)
        view_value = self.data.get(self.KEY_CAN_VIEW_VALUE, True)
        addr_idx = int(self.data.get(self.KEY_ACTIVE_ADDRESS_INDEX, 0))
        address = self.data.get(self.KEY_ACTIVE_ADDRESS)
        my_pools = self.data.get(self.KEY_MY_POOLS, [])
        if my_pools is None:
            my_pools = []

        inline_kbd = []

        button_toggle_show_value = InlineKeyboardButton(
            self.loc.BUTTON_VIEW_VALUE_ON if view_value else self.loc.BUTTON_VIEW_VALUE_OFF,
            callback_data=self.QUERY_BACK_TOGGLE_VIEW_VALUE)

        chain = Chains.detect_chain(address)
        chain = chain if chain else Chains.BTC  # fixme: how about other chains?

        buttons = [InlineKeyboardButton(cut_long_text(pool), callback_data=f'{self.QUERY_VIEW_POOL}:{pool}')
                   for pool in my_pools]
        buttons = grouper(2, buttons)
        inline_kbd += buttons
        inline_kbd += [
            [
                InlineKeyboardButton(self.loc.BUTTON_SM_SUMMARY,
                                     callback_data=f'{self.QUERY_SUMMARY_OF_ADDRESS}:{addr_idx}'),
                InlineKeyboardButton(self.loc.BUTTON_VIEW_RUNESTAKEINFO,
                                     url=get_runeyield_info_address(self.deps.cfg.network_id, address, chain))
            ]
        ]

        # remove this address button
        if not external:
            inline_kbd += [
                [
                    *([button_toggle_show_value] if my_pools else []),
                    InlineKeyboardButton(self.loc.BUTTON_REMOVE_THIS_ADDRESS,
                                         callback_data=f'{self.QUERY_REMOVE_ADDRESS}:{addr_idx}')
                ],
            ]

        # back button
        inline_kbd += [
            [
                InlineKeyboardButton(self.loc.BUTTON_SM_BACK_TO_LIST, callback_data=self.QUERY_BACK_TO_ADDRESS_LIST)
            ]
        ]

        return InlineKeyboardMarkup(inline_keyboard=inline_kbd)

    async def show_pool_menu_for_address(self, message: Message, address: str,
                                         reload_pools=True,
                                         edit=True,
                                         external=False):
        rune_yield = get_rune_yield_connector(self.deps)
        self.data[self.KEY_ACTIVE_ADDRESS] = address
        self.data[self.KEY_IS_EXTERNAL] = external

        if reload_pools:
            if edit:
                await message.edit_text(text=self.loc.text_stake_loading_pools(address))
            else:
                message = await message.answer(text=self.loc.text_stake_loading_pools(address),
                                               reply_markup=kbd([self.loc.BUTTON_SM_BACK_MM]))

            try:
                my_pools = await rune_yield.get_my_pools(address)
            except FileNotFoundError:
                logging.error(f'not found pools for address {address}')
                my_pools = []

            self.data[self.KEY_MY_POOLS] = my_pools

        await self.show_my_pools(message, edit=edit)

    async def on_selected_address(self, query: CallbackQuery, reload_pools=True):
        _, addr_idx = query.data.split(':')
        addr_idx = int(addr_idx)
        address = self.my_addresses[addr_idx].address
        self.data[self.KEY_ACTIVE_ADDRESS_INDEX] = addr_idx

        await self.show_pool_menu_for_address(query.message, address, reload_pools)

    async def show_my_pools(self, message: Message, edit):
        inline_kbd = self.kbd_for_pools()
        address = self.data[self.KEY_ACTIVE_ADDRESS]
        my_pools = self.data[self.KEY_MY_POOLS]

        text = self.loc.text_stake_provides_liq_to_pools(address, my_pools) if my_pools \
            else self.loc.TEXT_LP_NO_POOLS_FOR_THIS_ADDRESS
        if edit:
            await message.edit_text(text=text,
                                    reply_markup=inline_kbd,
                                    disable_web_page_preview=True)
        else:
            await message.answer(text=text,
                                 reply_markup=inline_kbd,
                                 disable_web_page_preview=True,
                                 disable_notification=True)

    async def view_pool_report(self, query: CallbackQuery):
        _, pool = query.data.split(':')
        address = self.data[self.KEY_ACTIVE_ADDRESS]

        # POST A LOADING STICKER
        sticker = await self.answer_loading_sticker(query.message)

        # WORK...
        rune_yield = get_rune_yield_connector(self.deps)
        lp_report = await rune_yield.generate_yield_report_single_pool(address, pool)

        # GENERATE A PICTURE
        value_hidden = not self.data.get(self.KEY_CAN_VIEW_VALUE, True)
        picture = await lp_pool_picture(lp_report, self.loc, value_hidden=value_hidden)
        picture_io = img_to_bio(picture, f'Thorchain_LP_{pool}_{today_str()}.png')

        # ANSWER
        await self.show_my_pools(query.message, edit=False)
        await query.message.answer_photo(picture_io,  # caption=self.loc.TEXT_LP_IMG_CAPTION,
                                         disable_notification=True)

        # CLEAN UP
        await asyncio.gather(self.safe_delete(query.message),
                             self.safe_delete(sticker))

    async def show_pools_again(self, query: CallbackQuery):
        active_addr_idx = self.data[self.KEY_ACTIVE_ADDRESS_INDEX]
        query.data = f"{self.QUERY_VIEW_ADDRESS}:{active_addr_idx}"
        await self.on_selected_address(query, reload_pools=False)

    async def view_address_summary(self, query: CallbackQuery):
        address = self.data[self.KEY_ACTIVE_ADDRESS]

        my_pools = self.data[self.KEY_MY_POOLS]
        if not my_pools:
            await query.message.answer(self.loc.TEXT_LP_NO_POOLS_FOR_THIS_ADDRESS)
            return

        # POST A LOADING STICKER
        sticker = await self.answer_loading_sticker(query.message)

        # WORK
        rune_yield = get_rune_yield_connector(self.deps)
        yield_summary = await rune_yield.generate_yield_summary(address, my_pools)

        # GENERATE A PICTURE
        value_hidden = not self.data.get(self.KEY_CAN_VIEW_VALUE, True)
        picture = await lp_address_summary_picture(list(yield_summary.reports),
                                                   yield_summary.charts,
                                                   self.loc, value_hidden=value_hidden)
        picture_io = img_to_bio(picture, f'Thorchain_LP_Summary_{today_str()}.png')

        # ANSWER
        await self.show_my_pools(query.message, edit=False)
        await query.message.answer_photo(picture_io,
                                         disable_notification=True)

        # CLEAN UP
        await asyncio.gather(self.safe_delete(query.message),
                             self.safe_delete(sticker))

    # ----------- HANDLERS ------------

    @message_handler(state=LPMenuStates.MAIN_MENU)
    async def on_enter(self, message: Message):
        if message.text == self.loc.BUTTON_SM_BACK_MM:
            await self.go_back(message)
        else:
            await LPMenuStates.MAIN_MENU.set()
            address = message.text.strip()
            if address:
                if LPAddress.validate_address(address):
                    self.add_address(address, Chains.BNB)
                else:
                    await message.answer(code(self.loc.TEXT_INVALID_ADDRESS),
                                         disable_notification=True)

            await self.display_addresses(message)
            msg = self.loc.TEXT_SELECT_ADDRESS_ABOVE if self.my_addresses else ''
            msg += self.loc.TEXT_SELECT_ADDRESS_SEND_ME
            await message.answer(msg, reply_markup=kbd([self.loc.BUTTON_SM_BACK_MM]),
                                 disable_notification=True)

    @query_handler(state=LPMenuStates.MAIN_MENU)
    async def on_tap_address(self, query: CallbackQuery):
        if query.data.startswith(f'{self.QUERY_VIEW_ADDRESS}:'):
            await self.on_selected_address(query)
        elif query.data == self.QUERY_BACK_TO_ADDRESS_LIST:
            await self.display_addresses(query.message, edit=True)
        elif query.data.startswith(f'{self.QUERY_REMOVE_ADDRESS}:'):
            _, index = query.data.split(':')
            self.remove_address(index)
            await self.display_addresses(query.message, edit=True)
        elif query.data.startswith(f'{self.QUERY_SUMMARY_OF_ADDRESS}:'):
            await self.view_address_summary(query)
        elif query.data.startswith(f'{self.QUERY_VIEW_POOL}:'):
            await self.view_pool_report(query)
        elif query.data == self.QUERY_BACK_TOGGLE_VIEW_VALUE:
            self.data[self.KEY_CAN_VIEW_VALUE] = not self.data.get(self.KEY_CAN_VIEW_VALUE, True)
            await self.show_pools_again(query)
