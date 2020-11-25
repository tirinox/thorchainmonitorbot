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


class StakeStates(StatesGroup):
    mode = HelperMode.snake_case
    MAIN_MENU = State()
    ADD_ADDRESS = State()


class StakeDialog(BaseDialog):
    DATA_KEY_MY_ADDR = 'my_addr'

    BUTTON_SM_ADD_ADDRESS = 'Add an address'
    BUTTON_BACK = 'Back'
    BUTTON_SM_BACK_TO_LIST = 'Back to list'

    @property
    def my_addresses(self):
        raw = self.data.get(self.DATA_KEY_MY_ADDR, [])
        return [MyStakeAddress(**j) for j in raw]

    def add_address(self, new_addr, chain=BNB_CHAIN):
        new_addr = str(new_addr).strip()
        current_list = self.my_addresses
        my_unique_addr = set((a.chain, a.address) for a in current_list)
        if (chain, new_addr) not in my_unique_addr:
            self.data[self.DATA_KEY_MY_ADDR] = [asdict(a) for a in current_list + [MyStakeAddress(new_addr)]]

    def remove_address(self, index):
        del self.data[self.DATA_KEY_MY_ADDR][int(index)]

    def addresses_kbd(self):
        buttons = []
        for i, addr in enumerate(self.my_addresses):
            data = f'view-addr:{i}'
            buttons.append(InlineKeyboardButton(short_address(addr.address, begin=10, end=7), callback_data=data))
        return InlineKeyboardMarkup(inline_keyboard=grouper(2, buttons))

    async def display_addresses(self, message: Message, edit=False):
        addresses = self.my_addresses
        f = message.edit_text if edit else message.answer
        kw = {} if edit else {'disable_notification': True}
        if not addresses:
            await message.answer("You have not added any addresses yet. Send me one.",
                                 reply_markup=kbd([self.BUTTON_BACK]),
                                 **kw)
        else:
            await f('Your addresses:',
                    reply_markup=self.addresses_kbd(), **kw)

    def kbd_for_pools(self):
        view_value = self.data.get('view-value', True)
        addr_idx = int(self.data.get('active_addr_idx', 0))
        my_pools = self.data.get('my_pools', [])

        inline_kbd = []
        buttons = [InlineKeyboardButton(pool, callback_data=f'view-pool:{pool}') for pool in my_pools]
        buttons = grouper(2, buttons)
        inline_kbd += buttons
        inline_kbd += [
            [
                InlineKeyboardButton('View value: ON' if view_value else 'View value: OFF',
                                     callback_data=f'toggle_view_value'),
                InlineKeyboardButton('Remove this address', callback_data=f'remove:{addr_idx}')
            ],
            [InlineKeyboardButton(self.BUTTON_SM_BACK_TO_LIST,
                                  callback_data=f'back_to_list')
             ]
        ]
        return inline_kbd

    async def on_selected_address(self, query: CallbackQuery, reload_pools=True):
        _, addr_idx = query.data.split(':')
        addr_idx = int(addr_idx)
        addr = self.my_addresses[addr_idx].address

        lpf = LiqPoolFetcher(self.deps)
        self.data['active_addr'] = addr
        self.data['active_addr_idx'] = addr_idx

        if reload_pools:
            await query.message.edit_text(text=f'Please wait. Loading pools for {pre(addr)}...')
            my_pools = await lpf.get_my_pools(addr)
            self.data['my_pools'] = my_pools

        inline_kbd = self.kbd_for_pools()
        await query.message.edit_text(text=f'Address: {pre(addr)} provides liquidity to the following pools:',
                                      reply_markup=InlineKeyboardMarkup(inline_keyboard=inline_kbd))

    async def view_pool_report(self, query: CallbackQuery):
        _, pool = query.data.split(':')
        addr = self.data['active_addr']
        sticker = await query.message.answer_sticker(LOADING_STICKER)

        lpf = LiqPoolFetcher(self.deps)
        liq = await lpf.fetch_one_pool_liquidity_info(addr, pool)

        ppf = PoolPriceFetcher(self.deps)
        stake_report = await lpf.fetch_stake_report_for_pool(liq, ppf)

        value_hidden = not self.data.get('view-value', True)
        picture = await lp_pool_picture(stake_report, value_hidden=value_hidden)
        picture_io = img_to_bio(picture, f'LP_{pool}.png')

        await query.message.answer_photo(picture_io)
        await sticker.delete()

    async def show_pools_again(self, query: CallbackQuery):
        query.data = f"view-addr:{self.data['active_addr_idx']}"
        await self.on_selected_address(query, reload_pools=False)

    # ----------- HANDLERS ------------

    @message_handler(state=StakeStates.MAIN_MENU)
    async def on_enter(self, message: Message):
        if message.text == self.BUTTON_BACK:
            await self.go_back(message)
        else:
            await StakeStates.MAIN_MENU.set()
            addr = message.text.strip()
            if addr:
                if MyStakeAddress.is_good_address(addr):
                    self.add_address(addr, BNB_CHAIN)
                else:
                    await message.answer(code('Invalid address!'))

            await self.display_addresses(message)
            msg = 'Select one from above. ☝️ ' if self.my_addresses else ''
            msg += 'If you want to add one more, please send me it. 👇'
            await message.answer(msg,
                                 reply_markup=kbd([self.BUTTON_BACK]))

    @query_handler(state=StakeStates.MAIN_MENU)
    async def on_tap_address(self, query: CallbackQuery):
        if query.data.startswith('view-addr:'):
            await self.on_selected_address(query)
        elif query.data == 'back_to_list':
            await self.display_addresses(query.message, edit=True)
        elif query.data.startswith('remove:'):
            _, index = query.data.split(':')
            self.remove_address(index)
            await self.display_addresses(query.message, edit=True)
        elif query.data.startswith('view-pool:'):
            await self.view_pool_report(query)
            inline_kbd = self.kbd_for_pools()
            addr = self.data['active_addr']
            await query.message.answer(text=f'Address: {pre(addr)} provides liquidity to the following pools:',
                                       reply_markup=InlineKeyboardMarkup(inline_keyboard=inline_kbd))
        elif query.data == 'toggle_view_value':
            self.data['view-value'] = not self.data.get('view-value', True)
            await self.show_pools_again(query)
