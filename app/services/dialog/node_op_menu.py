from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.helper import HelperMode

from services.dialog.base import BaseDialog, message_handler, query_handler
from services.lib.telegram import TelegramInlineList
from services.lib.texts import kbd
from services.models.node_watchers import NodeWatcherStorage


class NodeOpStates(StatesGroup):
    mode = HelperMode.snake_case
    MAIN_MENU = State()
    ADDING = State()
    MANAGE_MENU = State()


TEST_ITEMS = [f'Item {n}.' for n in range(1, 35)]


class NodeOpDialog(BaseDialog):
    # ----------- HANDLERS ------------

    @message_handler(state=NodeOpStates.all_states)
    async def on_enter(self, message: Message):
        if message.text == self.loc.BUTTON_BACK:
            await self.go_back(message)
            return
        elif message.text == self.loc.BUTTON_NOP_ADD_NODES:
            ...
        elif message.text == self.loc.BUTTON_NOP_MANAGE_NODES:
            await self.on_manage(message)
        elif message.text == self.loc.BUTTON_NOP_SETTINGS:
            ...
        else:
            await self.show_menu(message)

    @query_handler(state=NodeOpStates.MAIN_MENU)
    async def on_main_callback(self, query: CallbackQuery):
        ...

    def node_list_maker(self):
        return TelegramInlineList(TEST_ITEMS, data_proxy=self.data,
                                  max_rows=4, back_text=self.loc.BUTTON_BACK, data_prefix='node_list')

    async def on_manage(self, message: Message):
        await NodeOpStates.MANAGE_MENU.set()
        keyboard = self.node_list_maker().reset_page().keyboard()
        await message.answer('List test:', reply_markup=keyboard)

    @query_handler(state=NodeOpStates.MANAGE_MENU)
    async def on_manage_callback(self, query: CallbackQuery):
        result = await self.node_list_maker().handle_query(query)
        if result.result == result.BACK:
            await self.on_enter(query.message)
        elif result.result == result.SELECTED:
            print(f'Selected {result.selected_item}')

    async def show_menu(self, message: Message):
        await NodeOpStates.MAIN_MENU.set()
        buttons = [
            [self.loc.BUTTON_NOP_ADD_NODES, self.loc.BUTTON_NOP_MANAGE_NODES],
            [self.loc.BUTTON_NOP_SETTINGS, self.loc.BUTTON_BACK]
        ]

        watch_list = await NodeWatcherStorage(self.deps, message.from_user.id).all_nodes_with_names_for_user()
        await message.answer(self.loc.text_node_op_welcome_text(watch_list),
                             reply_markup=kbd(buttons),
                             disable_notification=True)
