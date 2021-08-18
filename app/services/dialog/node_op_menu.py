from typing import List

import aiogram.types
from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, ReplyKeyboardRemove
from aiogram.utils.helper import HelperMode

from services.dialog.base import BaseDialog, message_handler, query_handler
from services.jobs.fetch.node_info import NodeInfoFetcher
from services.lib.telegram import TelegramInlineList
from services.lib.texts import kbd, join_as_numbered_list
from services.lib.utils import parse_list_from_string, fuzzy_search
from services.models.node_info import NodeInfo
from services.models.node_watchers import NodeWatcherStorage


class NodeOpStates(StatesGroup):
    mode = HelperMode.snake_case
    MAIN_MENU = State()
    ADDING = State()
    MANAGE_MENU = State()


class NodeOpDialog(BaseDialog):

    # ----------- MAIN ------------

    @message_handler(state=NodeOpStates.MAIN_MENU)
    async def on_enter(self, message: Message):
        if message.text == self.loc.BUTTON_BACK:
            await self.go_back(message)
        elif message.text == self.loc.BUTTON_NOP_ADD_NODES:
            await self.on_add_node_menu(message)
        elif message.text == self.loc.BUTTON_NOP_MANAGE_NODES:
            await self.on_manage_menu(message)
        elif message.text == self.loc.BUTTON_NOP_SETTINGS:
            await self.on_settings_menu(message)
        else:
            await self.show_menu(message)

    async def show_menu(self, message: Message):
        await NodeOpStates.MAIN_MENU.set()
        buttons = [
            [self.loc.BUTTON_NOP_ADD_NODES, self.loc.BUTTON_NOP_MANAGE_NODES],
            [self.loc.BUTTON_NOP_SETTINGS, self.loc.BUTTON_BACK]
        ]

        watch_list = await self.storage(message.chat.id).all_nodes_with_names_for_user()
        await message.answer(self.loc.text_node_op_welcome_text(watch_list),
                             reply_markup=kbd(buttons),
                             disable_notification=True)

    # @query_handler(state=NodeOpStates.MAIN_MENU)
    # async def on_main_callback(self, query: CallbackQuery):
    #     ...

    # -------- ADDING ---------

    async def all_nodes_list_maker(self):
        last_nodes = await self.get_all_nodes()
        last_node_texts = [self.loc.short_node_desc(n) for n in last_nodes]
        return TelegramInlineList(
            last_node_texts,
            data_proxy=self.data,
            max_rows=3, back_text=self.loc.BUTTON_BACK,
            data_prefix='all_nodes'
        ).set_extra_buttons_above([
            [
                InlineKeyboardButton(self.loc.BUTTON_NOP_ADD_ALL_NODES, callback_data='add:all'),
                InlineKeyboardButton(self.loc.BUTTON_NOP_ADD_ALL_ACTIVE_NODES, callback_data='add:active')
            ]
        ])

    async def on_add_node_menu(self, message: Message):
        await NodeOpStates.ADDING.set()
        tg_list = await self.all_nodes_list_maker()
        # to hide KB
        await message.answer(self.loc.TEXT_NOP_ADD_INSTRUCTIONS_PRE, reply_markup=ReplyKeyboardRemove())
        await message.answer(self.loc.TEXT_NOP_ADD_INSTRUCTIONS, reply_markup=tg_list.reset_page().keyboard())

    @message_handler(state=NodeOpStates.ADDING)
    async def on_add_got_message(self, message: Message):
        nodes = await self.parse_nodes_from_text_list(message.text)
        if not nodes:
            await message.answer(self.loc.TEXT_NOP_SEARCH_NO_VARIANTS)
        else:
            variants = join_as_numbered_list(map(self.loc.pretty_node_desc, nodes))
            await message.answer(self.loc.TEXT_NOP_SEARCH_VARIANTS + '\n\n' + variants)

    @query_handler(state=NodeOpStates.ADDING)
    async def on_add_list_callback(self, query: CallbackQuery):
        tg_list = await self.all_nodes_list_maker()
        result = await tg_list.handle_query(query)
        if result.result == result.BACK:
            await self.on_enter(query.message)
        elif result.result == result.SELECTED:
            await query.message.answer(f'You selected {result.selected_item}')
        elif query.data == 'add:all':
            await query.message.answer(f'Adding all!')  # todo
        elif query.data == 'add:active':
            await query.message.answer(f'Adding all active!')  # todo

    # -------- MANAGE ---------

    async def my_node_list_maker(self, user_id):
        watch_list = await self.storage(user_id).all_nodes_with_names_for_user()
        my_nodes_names = [self.loc.short_node_name(*pair) for pair in watch_list.items()]
        return TelegramInlineList(my_nodes_names, data_proxy=self.data,
                                  max_rows=4, back_text=self.loc.BUTTON_BACK, data_prefix='my_nodes')

    async def on_manage_menu(self, message: Message):
        await NodeOpStates.MANAGE_MENU.set()
        tg_list = await self.my_node_list_maker(message.chat.id)
        keyboard = tg_list.reset_page().keyboard()
        await message.answer(self.loc.TEXT_NOP_MANAGE, reply_markup=keyboard)

    @query_handler(state=NodeOpStates.MANAGE_MENU)
    async def on_manage_callback(self, query: CallbackQuery):
        tg_list = await self.my_node_list_maker(query.message.chat.id)
        result = await tg_list.handle_query(query)
        if result.result == result.BACK:
            await self.on_enter(query.message)
        elif result.result == result.SELECTED:
            await query.message.answer(f'You selected {result.selected_item}')

    # -------- SETTINGS ---------

    async def on_settings_menu(self, message: Message):
        await message.answer('Not implemented yet..')  # todo: implement settings menu

    # ---- UTILS ---

    def storage(self, user_id):
        return NodeWatcherStorage(self.deps, user_id)

    async def get_all_nodes(self):
        node_info_fetcher: NodeInfoFetcher = self.deps.node_info_fetcher
        return await node_info_fetcher.get_last_node_info()

    async def parse_nodes_from_text_list(self, message: str) -> List[NodeInfo]:
        user_items = parse_list_from_string(message, upper=True)  # parse
        user_items = [item for item in user_items if len(item) >= 3]  # filter short

        # run fuzzy search
        nodes = await self.get_all_nodes()
        node_addresses = [n.node_address.upper() for n in nodes]
        results = set()
        for query in user_items:
            variants = fuzzy_search(query, node_addresses)
            results.update(set(variants))

        # pick node info
        nodes_dic = {node.node_address.upper(): node for node in nodes}
        return list(filter(bool, (nodes_dic.get(address) for address in results)))
