from dataclasses import asdict

from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.types import *
from aiogram.utils.helper import HelperMode

from localization.base import kbd
from services.dialog.base import BaseDialog, tg_filters
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

    @tg_filters(state=StakeStates.MAIN_MENU)
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

            addresses = [
                MyStakeAddress.from_json(j) for j in self.data.get(self.DATA_KEY_MY_ADDR, [])
            ]
            if not addresses:
                await message.answer("You didn't add addresses. Send me one.",
                                     reply_markup=kbd([self.BUTTON_BACK]),
                                     disable_notification=True)
            else:
                items = []
                for addr in addresses:
                    data = f'{addr.chain}:{addr.address}'
                    items.append([
                        InlineKeyboardButton(short_address(addr.address, begin=10, end=7), callback_data=data)
                    ])
                await message.answer('Your addresses:',
                                     reply_markup=InlineKeyboardMarkup(inline_keyboard=items))
                await message.answer('Select one of above. ☝️ If you want to add one more, please send me it. 👇',
                                     reply_markup=kbd([self.BUTTON_BACK]))