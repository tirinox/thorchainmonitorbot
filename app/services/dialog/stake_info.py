from dataclasses import asdict

from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.types import *
from aiogram.utils.helper import HelperMode

from localization.base import kbd
from services.dialog.base import BaseDialog, message_handler, query_handler
from services.dialog.lp_picture import lp_pool_picture, img_to_bio
from services.fetch.lp import LiqPoolFetcher
from services.fetch.pool_price import PoolPriceFetcher
from services.lib.money import short_address
from services.lib.utils import code, pre, grouper
from services.models.stake_info import MyStakeAddress, BNB_CHAIN

LOADING_STICKER = 'CAACAgIAAxkBAAIRx1--Tia-m6DNRIApk3yqmNWvap_sAALcAAP3AsgPUNi8Bnu98HweBA'
RUNE_STAKE_INFO = 'https://runestake.info/debug?address={address}'


class StakeStates(StatesGroup):
    mode = HelperMode.snake_case
    MAIN_MENU = State()


class StakeDialog(BaseDialog):
    QUERY_VIEW_ADDRESS = 'view-addr'
    QUERY_REMOVE_ADDRESS = 'remove-addr'
    QUERY_BACK_TO_ADDRESS_LIST = 'back-to-addr-list'
    QUERY_BACK_TOGGLE_VIEW_VALUE = 'toggle-view-value'
    QUERY_VIEW_POOL = 'view-pool'

    KEY_MY_ADDRESSES = 'my-address-list'
    KEY_CAN_VIEW_VALUE = 'can-view-value'
    KEY_ACTIVE_ADDRESS = 'active-addr'
    KEY_ACTIVE_ADDRESS_INDEX = 'active-addr-id'
    KEY_MY_POOLS = 'my-pools'

    @property
    def my_addresses(self):
        raw = self.data.get(self.KEY_MY_ADDRESSES, [])
        return [MyStakeAddress(**j) for j in raw]

    def add_address(self, new_addr, chain=BNB_CHAIN):
        new_addr = str(new_addr).strip()
        current_list = self.my_addresses
        my_unique_addr = set((a.chain, a.address) for a in current_list)
        if (chain, new_addr) not in my_unique_addr:
            self.data[self.KEY_MY_ADDRESSES] = [asdict(a) for a in current_list + [MyStakeAddress(new_addr)]]

    def remove_address(self, index):
        del self.data[self.KEY_MY_ADDRESSES][int(index)]

    def addresses_kbd(self):
        buttons = []
        for i, addr in enumerate(self.my_addresses):
            data = f'{self.QUERY_VIEW_ADDRESS}:{i}'
            buttons.append(InlineKeyboardButton(short_address(addr.address, begin=10, end=7), callback_data=data))
        return InlineKeyboardMarkup(inline_keyboard=grouper(2, buttons))

    async def display_addresses(self, message: Message, edit=False):
        addresses = self.my_addresses
        f = message.edit_text if edit else message.answer
        kw = {} if edit else {'disable_notification': True}
        if not addresses:
            await message.answer(self.loc.TEXT_NO_ADDRESSES,
                                 reply_markup=kbd([self.loc.BUTTON_BACK]),
                                 **kw)
        else:
            await f(self.loc.TEXT_YOUR_ADDRESSES, reply_markup=self.addresses_kbd(), **kw)

    def kbd_for_pools(self):
        view_value = self.data.get(self.KEY_CAN_VIEW_VALUE, True)
        addr_idx = int(self.data.get(self.KEY_ACTIVE_ADDRESS_INDEX, 0))
        address = self.data.get(self.KEY_ACTIVE_ADDRESS)
        my_pools = self.data.get(self.KEY_MY_POOLS, [])

        inline_kbd = []
        buttons = [InlineKeyboardButton(pool, callback_data=f'{self.QUERY_VIEW_POOL}:{pool}') for pool in my_pools]
        buttons = grouper(2, buttons)
        inline_kbd += buttons
        inline_kbd += [
            [
                InlineKeyboardButton(self.loc.BUTTON_VIEW_RUNESTAKEINFO, url=RUNE_STAKE_INFO.format(address=address))
            ],
            [
                InlineKeyboardButton(self.loc.BUTTON_VIEW_VALUE_ON if view_value else self.loc.BUTTON_VIEW_VALUE_OFF,
                                     callback_data=self.QUERY_BACK_TOGGLE_VIEW_VALUE),
                InlineKeyboardButton(self.loc.BUTTON_REMOVE_THIS_ADDRESS,
                                     callback_data=f'{self.QUERY_REMOVE_ADDRESS}:{addr_idx}')
            ],
            [
                InlineKeyboardButton(self.loc.BUTTON_SM_BACK_TO_LIST, callback_data=self.QUERY_BACK_TO_ADDRESS_LIST)
            ]
        ]
        return InlineKeyboardMarkup(inline_keyboard=inline_kbd)

    async def on_selected_address(self, query: CallbackQuery, reload_pools=True):
        _, addr_idx = query.data.split(':')
        addr_idx = int(addr_idx)
        address = self.my_addresses[addr_idx].address

        lpf = LiqPoolFetcher(self.deps)
        self.data[self.KEY_ACTIVE_ADDRESS] = address
        self.data[self.KEY_ACTIVE_ADDRESS_INDEX] = addr_idx

        if reload_pools:
            await query.message.edit_text(text=self.loc.text_stake_loading_pools(address))
            my_pools = await lpf.get_my_pools(address)
            self.data[self.KEY_MY_POOLS] = my_pools
        else:
            my_pools = self.data[self.KEY_MY_POOLS]

        inline_kbd = self.kbd_for_pools()
        await query.message.edit_text(text=self.loc.text_stake_provides_liq_to_pools(address, my_pools),
                                      reply_markup=inline_kbd,
                                      disable_web_page_preview=True)

    async def list_pools_new_message(self, query: CallbackQuery):
        inline_kbd = self.kbd_for_pools()
        address = self.data[self.KEY_ACTIVE_ADDRESS]
        my_pools = self.data[self.KEY_MY_POOLS]
        await query.message.answer(text=self.loc.text_stake_provides_liq_to_pools(address, my_pools),
                                   reply_markup=inline_kbd,
                                   disable_web_page_preview=True,
                                   disable_notification=True)

    async def view_pool_report(self, query: CallbackQuery):
        _, pool = query.data.split(':')
        address = self.data[self.KEY_ACTIVE_ADDRESS]
        sticker = await query.message.answer_sticker(LOADING_STICKER,
                                                     disable_notification=True)

        lpf = LiqPoolFetcher(self.deps)
        liq = await lpf.fetch_one_pool_liquidity_info(address, pool)

        ppf = PoolPriceFetcher(self.deps)
        stake_report = await lpf.fetch_stake_report_for_pool(liq, ppf)

        value_hidden = not self.data.get(self.KEY_CAN_VIEW_VALUE, True)
        picture = await lp_pool_picture(stake_report, self.loc, value_hidden=value_hidden)
        picture_io = img_to_bio(picture, f'Thorchain_LP_{pool}.png')

        await query.message.answer_photo(picture_io,
                                         disable_notification=True)
        await sticker.delete()

    async def show_pools_again(self, query: CallbackQuery):
        active_addr_idx = self.data[self.KEY_ACTIVE_ADDRESS_INDEX]
        query.data = f"{self.QUERY_VIEW_ADDRESS}:{active_addr_idx}"
        await self.on_selected_address(query, reload_pools=False)

    # ----------- HANDLERS ------------

    @message_handler(state=StakeStates.MAIN_MENU)
    async def on_enter(self, message: Message):
        if message.text == self.loc.BUTTON_BACK:
            await self.go_back(message)
        else:
            await StakeStates.MAIN_MENU.set()
            address = message.text.strip()
            if address:
                if MyStakeAddress.is_good_address(address):
                    self.add_address(address, BNB_CHAIN)
                else:
                    await message.answer(code(self.loc.TEXT_INVALID_ADDRESS),
                                         disable_notification=True)

            await self.display_addresses(message)
            msg = self.loc.TEXT_SELECT_ADDRESS_ABOVE if self.my_addresses else ''
            msg += self.loc.TEXT_SELECT_ADDRESS_SEND_ME
            await message.answer(msg, reply_markup=kbd([self.loc.BUTTON_BACK]),
                                 disable_notification=True)

    @query_handler(state=StakeStates.MAIN_MENU)
    async def on_tap_address(self, query: CallbackQuery):
        if query.data.startswith(f'{self.QUERY_VIEW_ADDRESS}:'):
            await self.on_selected_address(query)
        elif query.data == self.QUERY_BACK_TO_ADDRESS_LIST:
            await self.display_addresses(query.message, edit=True)
        elif query.data.startswith(f'{self.QUERY_REMOVE_ADDRESS}:'):
            _, index = query.data.split(':')
            self.remove_address(index)
            await self.display_addresses(query.message, edit=True)
        elif query.data.startswith(f'{self.QUERY_VIEW_POOL}:'):
            await self.view_pool_report(query)
            await self.list_pools_new_message(query)
        elif query.data == self.QUERY_BACK_TOGGLE_VIEW_VALUE:
            self.data[self.KEY_CAN_VIEW_VALUE] = not self.data.get(self.KEY_CAN_VIEW_VALUE, True)
            await self.show_pools_again(query)
