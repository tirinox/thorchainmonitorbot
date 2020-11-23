from dataclasses import asdict

from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.types import *
from aiogram.utils.helper import HelperMode

from localization.base import kbd
from services.dialog.base import BaseDialog, message_handler, query_handler
from services.lib.money import short_address
from services.lib.utils import code
from services.models.stake_info import MyStakeAddress, BNB_CHAIN


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

    def remove_address(self, addr, chain=BNB_CHAIN):
        self.data[self.DATA_KEY_MY_ADDR] = [asdict(a) for a in self.my_addresses
                                            if a.address != addr or a.chain != chain]

    def addresses_kbd(self, action='view'):
        items = []
        for addr in self.my_addresses:
            data = f'{action}:{addr.chain}:{addr.address}'
            items.append([
                InlineKeyboardButton(short_address(addr.address, begin=10, end=7), callback_data=data)
            ])
        return InlineKeyboardMarkup(inline_keyboard=items)

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
            await message.answer('Select one from above. ☝️ If you want to add one more, please send me it. 👇',
                                 reply_markup=kbd([self.BUTTON_BACK]))

    @query_handler(state=StakeStates.MAIN_MENU)
    async def on_tap_address(self, query: CallbackQuery):
        if query.data.startswith('view:'):
            _, chain, addr = query.data.split(':')
            await query.message.edit_text(text=f'Address: {addr}',
                                          reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                              [InlineKeyboardButton('Remove', callback_data=f'remove:{chain}:{addr}')],
                                              [InlineKeyboardButton(self.BUTTON_SM_BACK_TO_LIST,
                                                                    callback_data=f'back_to_list')]
                                          ]))
        elif query.data == 'back_to_list':
            await self.display_addresses(query.message, edit=True)
        elif query.data.startswith('remove:'):
            _, chain, addr = query.data.split(':')
            self.remove_address(addr, chain)
            await self.display_addresses(query.message, edit=True)
