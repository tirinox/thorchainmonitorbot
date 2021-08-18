from typing import List

import aiogram.types
from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup
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
        last_node_texts = [
            (self.loc.short_node_desc(n), n.node_address) for n in last_nodes
        ]
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
        if message.text == self.loc.BUTTON_BACK:
            await self.show_menu(message)
            return

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
            await self.add_nodes_for_user(query.message, [result.selected_data_tag], query.message.chat.id)
        elif query.data == 'add:all':
            last_nodes = await self.get_all_nodes()
            await self.add_nodes_for_user(query.message, [n.node_address for n in last_nodes], query.message.chat.id)
        elif query.data == 'add:active':
            last_nodes = await self.get_all_active_nodes()
            await self.add_nodes_for_user(query.message, [n.node_address for n in last_nodes], query.message.chat.id)
        await query.answer()

    async def add_nodes_for_user(self, message: Message, node_list: list, user_id):
        if not node_list:
            return
        await self.storage(user_id).add_user_to_node_list(node_list)
        await message.edit_text(self.loc.text_nop_success_add(node_list), reply_markup=InlineKeyboardMarkup())
        await self.show_menu(message)

    # -------- MANAGE ---------

    async def my_node_list_maker(self, user_id):
        watch_list = await self.storage(user_id).all_nodes_with_names_for_user()

        disconnected_addresses, inactive_addresses = await self.filter_user_nodes_by_category(list(watch_list.keys()))

        my_nodes_names = [self.loc.short_node_name(*pair) for pair in watch_list.items()]
        return TelegramInlineList(
            my_nodes_names, data_proxy=self.data,
            max_rows=4, back_text=self.loc.BUTTON_BACK, data_prefix='my_nodes'
        ).set_extra_buttons_below([[
            InlineKeyboardButton(
                self.loc.BUTTON_NOP_CLEAR_LIST.format(n=len(watch_list)),
                callback_data='del:all'
            ),
            InlineKeyboardButton(
                self.loc.BUTTON_NOP_REMOVE_INACTIVE.format(n=len(inactive_addresses)),
                callback_data='del:inactive'
            ),
            InlineKeyboardButton(
                self.loc.BUTTON_NOP_REMOVE_DISCONNECTED.format(n=len(disconnected_addresses)),
                callback_data='del:disconnected'
            ),
        ]])

    async def on_manage_menu(self, message: Message):
        await NodeOpStates.MANAGE_MENU.set()
        tg_list = await self.my_node_list_maker(message.chat.id)
        keyboard = tg_list.reset_page().keyboard()
        await message.answer(self.loc.TEXT_NOP_MANAGE_LIST_TITLE.format(n=len(tg_list)), reply_markup=keyboard)

    @query_handler(state=NodeOpStates.MANAGE_MENU)
    async def on_manage_callback(self, query: CallbackQuery):
        tg_list = await self.my_node_list_maker(query.message.chat.id)
        result = await tg_list.handle_query(query)
        if result.result == result.BACK:
            await self.on_enter(query.message)
        elif result.result == result.SELECTED:
            await query.message.answer(f'You selected {result.selected_item}')
        await query.answer()

    # -------- SETTINGS ---------

    async def on_settings_menu(self, message: Message):
        await message.answer('Not implemented yet..')  # todo: implement settings menu

    # ---- UTILS ---

    def storage(self, user_id):
        return NodeWatcherStorage(self.deps, user_id)

    async def get_all_nodes(self):
        node_info_fetcher: NodeInfoFetcher = self.deps.node_info_fetcher
        return await node_info_fetcher.get_last_node_info()

    async def get_all_active_nodes(self):
        nodes = await self.get_all_nodes()
        return [n for n in nodes if n.is_active]

    async def get_all_inactive_nodes(self):
        nodes = await self.get_all_nodes()
        return [n for n in nodes if not n.is_active]

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

    async def filter_user_nodes_by_category(self, node_addresses):
        real_nodes = await self.get_all_nodes()
        real_nodes_map = {n.node_address: n for n in real_nodes}
        disconnected_addresses = set()
        inactive_addresses = set()
        for address in node_addresses:
            node_info: NodeInfo = real_nodes_map.get(address)
            if node_info is None:
                disconnected_addresses.add(address)
            elif not node_info.is_active:
                inactive_addresses.add(address)

        return disconnected_addresses, inactive_addresses
