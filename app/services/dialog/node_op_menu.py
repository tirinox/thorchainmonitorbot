from typing import List

from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.helper import HelperMode

from services.dialog.base import BaseDialog, message_handler, query_handler
from services.jobs.node_churn import NodeStateDatabase
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
    SETTINGS = State()




class NodeOpDialog(BaseDialog):
    # ----------- MAIN ------------
    @message_handler(state=NodeOpStates.MAIN_MENU)
    async def on_handle_main_menu(self, message: Message):
        if message.text == self.loc.BUTTON_BACK:
            await self.go_back(message)
        else:
            return False
        return True

    async def show_main_menu(self, message: Message, with_welcome=True):
        await NodeOpStates.MAIN_MENU.set()

        watch_list = await self.storage(message.chat.id).all_nodes_with_names_for_user()

        inline_kbd = [
            [
                InlineKeyboardButton(self.loc.BUTTON_NOP_ADD_NODES, callback_data='mm:add'),
                InlineKeyboardButton(self.loc.BUTTON_NOP_MANAGE_NODES, callback_data='mm:edit')
            ],
            [
                InlineKeyboardButton(self.loc.BUTTON_NOP_SETTINGS, callback_data='mm:settings'),
                # InlineKeyboardButton(self.loc.BUTTON_BACK)  # not needed
            ]
        ]

        if with_welcome:
            await message.answer(self.loc.text_node_op_welcome_text_part1(),
                                 reply_markup=kbd([[self.loc.BUTTON_BACK]]))
            await message.answer(self.loc.text_node_op_welcome_text_part2(watch_list),
                                 reply_markup=InlineKeyboardMarkup(inline_keyboard=inline_kbd),
                                 disable_notification=True)
        else:
            await message.edit_text(self.loc.text_node_op_welcome_text_part2(watch_list),
                                    reply_markup=InlineKeyboardMarkup(inline_keyboard=inline_kbd))

    @query_handler(state=NodeOpStates.MAIN_MENU)
    async def on_main_menu_callback(self, query: CallbackQuery):
        if query.data == 'mm:add':
            await self.on_add_node_menu(query.message)
        elif query.data == 'mm:edit':
            await self.on_manage_menu(query.message)
        elif query.data == 'mm:settings':
            await self.on_settings_menu(query.message)
        await query.answer()

    # -------- ADDING ---------

    async def all_nodes_list_maker(self):
        last_nodes = await self.get_all_nodes()
        last_node_texts = [
            # add node_address as a tag
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
        # await message.answer(self.loc.TEXT_NOP_ADD_INSTRUCTIONS_PRE, reply_markup=ReplyKeyboardRemove())
        # await message.answer(self.loc.TEXT_NOP_ADD_INSTRUCTIONS, reply_markup=tg_list.reset_page().keyboard())

        await message.edit_text(
            self.loc.TEXT_NOP_ADD_INSTRUCTIONS_PRE + '\n\n' +
            self.loc.TEXT_NOP_ADD_INSTRUCTIONS, reply_markup=tg_list.reset_page().keyboard())

    @message_handler(state=NodeOpStates.ADDING)
    async def on_add_got_message(self, message: Message):
        if message.text == self.loc.BUTTON_BACK:
            await self.show_main_menu(message, with_welcome=True)
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

        user_id = query.message.chat.id

        if result.result == result.BACK:
            await self.show_main_menu(query.message, with_welcome=False)
        elif result.result == result.SELECTED:
            await self.add_nodes_for_user(query, [result.selected_data_tag], user_id, go_back=False)
        elif query.data == 'add:all':
            last_nodes = await self.get_all_nodes()
            await self.add_nodes_for_user(query, [n.node_address for n in last_nodes], user_id)
        elif query.data == 'add:active':
            last_nodes = await self.get_all_active_nodes()
            await self.add_nodes_for_user(query, [n.node_address for n in last_nodes], user_id)

    async def add_nodes_for_user(self, query: CallbackQuery, node_list: list, user_id, go_back=True):
        if not node_list:
            return
        await self.storage(user_id).add_user_to_node_list(node_list)
        await query.answer(self.loc.text_nop_success_add_banner(node_list))
        if go_back:
            await self.show_main_menu(query.message)

    # -------- MANAGE ---------

    async def my_node_list_maker(self, user_id):
        watch_list = await self.storage(user_id).all_nodes_with_names_for_user()

        disconnected_addresses, inactive_addresses = await self.filter_user_nodes_by_category(list(watch_list.keys()))

        my_nodes_names = [
            # add node_address as a tag
            (self.loc.short_node_name(address, name), address) for address, name in watch_list.items()
        ]

        extra_row = []
        if watch_list:
            extra_row.append(InlineKeyboardButton(
                self.loc.BUTTON_NOP_CLEAR_LIST.format(n=len(watch_list)),
                callback_data='del:all'
            ))

        if inactive_addresses:
            extra_row.append(InlineKeyboardButton(
                self.loc.BUTTON_NOP_REMOVE_INACTIVE.format(n=len(inactive_addresses)),
                callback_data='del:inactive'
            ))

        if disconnected_addresses:
            extra_row.append(InlineKeyboardButton(
                self.loc.BUTTON_NOP_REMOVE_DISCONNECTED.format(n=len(disconnected_addresses)),
                callback_data='del:disconnected'
            ))

        return TelegramInlineList(
            my_nodes_names, data_proxy=self.data,
            max_rows=4, back_text=self.loc.BUTTON_BACK, data_prefix='my_nodes'
        ).set_extra_buttons_above([extra_row])

    async def on_manage_menu(self, message: Message):
        await NodeOpStates.MANAGE_MENU.set()
        tg_list = await self.my_node_list_maker(message.chat.id)
        keyboard = tg_list.reset_page().keyboard()
        await message.edit_text(self.loc.TEXT_NOP_MANAGE_LIST_TITLE.format(n=len(tg_list)), reply_markup=keyboard)

    @query_handler(state=NodeOpStates.MANAGE_MENU)
    async def on_manage_callback(self, query: CallbackQuery):
        user_id = query.message.chat.id
        tg_list = await self.my_node_list_maker(user_id)
        result = await tg_list.handle_query(query)

        watch_list = await self.storage(user_id).all_nodes_for_user()
        disconnected_addresses, inactive_addresses = await self.filter_user_nodes_by_category(list(watch_list))

        if result.result == result.BACK:
            await self.show_main_menu(query.message, with_welcome=False)
        elif result.result == result.SELECTED:
            await self.remove_nodes_for_user(query, [result.selected_data_tag], user_id, go_back=False)
        elif query.data == 'del:all':
            await self.remove_nodes_for_user(query, watch_list, user_id)
        elif query.data == 'del:inactive':
            await self.remove_nodes_for_user(query, inactive_addresses, user_id)
        elif query.data == 'del:disconnected':
            await self.remove_nodes_for_user(query, disconnected_addresses, user_id)

    async def remove_nodes_for_user(self, query: CallbackQuery, node_list: iter, user_id, go_back=True):
        if not node_list:
            return

        await self.storage(user_id).remove_user_nodes(node_list)

        await query.answer(self.loc.text_nop_success_remove_banner(node_list))
        if go_back:
            await self.show_main_menu(query.message, with_welcome=False)
        else:
            await self.on_manage_menu(query.message)

    # -------- SETTINGS ---------

    async def on_settings_menu(self, message: Message):
        # todo: implement settings menu
        await NodeOpStates.SETTINGS.set()
        await message.edit_text('Not implemented yet..', reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(self.loc.BUTTON_BACK, callback_data='setting:back')
            ]]
        ))

    @query_handler(state=NodeOpStates.SETTINGS)
    # todo: implement settings menu
    async def on_setting_callback(self, query: CallbackQuery):
        if query.data == 'setting:back':
            await self.show_main_menu(query.message, with_welcome=False)
        await query.answer()

    # ---- UTILS ---

    def storage(self, user_id):
        return NodeWatcherStorage(self.deps, user_id)

    async def get_all_nodes(self):
        return await NodeStateDatabase(self.deps).get_last_node_info_list()

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

    @classmethod
    def is_enabled(cls, cfg):
        return bool(cfg.get('telegram.menu.node_op_tools.enabled', default=False))
