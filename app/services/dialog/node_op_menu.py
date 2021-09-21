from typing import List

from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from aiogram.utils.helper import HelperMode

from services.dialog.base import BaseDialog, message_handler, query_handler
from services.jobs.node_churn import NodeStateDatabase
from services.lib.date_utils import MINUTE
from services.lib.telegram import TelegramInlineList
from services.lib.texts import join_as_numbered_list
from services.lib.utils import parse_list_from_string, fuzzy_search
from services.models.node_info import NodeInfo
from services.models.node_watchers import NodeWatcherStorage
from services.notify.personal.helpers import NodeOpSetting


class NodeOpStates(StatesGroup):
    mode = HelperMode.snake_case
    MAIN_MENU = State()
    ADDING = State()
    MANAGE_MENU = State()
    SETTINGS = State()
    SETT_SLASH_ENABLED = State()
    SETT_SLASH_PERIOD = State()
    SETT_SLASH_THRESHOLD = State()
    SETT_BOND_ENABLED = State()
    SETT_NEW_VERSION_ENABLED = State()
    SETT_UPDATE_VERSION_ENABLED = State()
    SETT_CHURNING_ENABLED = State()
    SETT_OFFLINE_ENABLED = State()
    SETT_HEIGHT_ENABLED = State()
    SETT_HEIGHT_LAG_TIME = State()


class NodeOpDialog(BaseDialog):
    # ----------- MAIN ------------
    # @message_handler(state=NodeOpStates.MAIN_MENU)
    # async def on_handle_main_menu(self, message: Message):
    #     if message.text == self.loc.BUTTON_BACK:
    #         await self.go_back(message)
    #     else:
    #         return False
    #     return True

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
                InlineKeyboardButton(self.loc.BUTTON_BACK, callback_data='back')
            ]
        ]

        text = self.loc.text_node_op_welcome_text_part2(watch_list, self.deps.node_op_notifier.last_signal_sec_ago)
        if with_welcome:
            await message.answer(self.loc.TEXT_NOP_INTRO_HEADING,
                                 reply_markup=ReplyKeyboardRemove(),
                                 disable_notification=True)
            await message.answer(text,
                                 reply_markup=InlineKeyboardMarkup(inline_keyboard=inline_kbd),
                                 disable_notification=True)
        else:
            await message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=inline_kbd))

    @query_handler(state=NodeOpStates.MAIN_MENU)
    async def on_main_menu_callback(self, query: CallbackQuery):
        if query.data == 'mm:add':
            await self.on_add_node_menu(query.message)
        elif query.data == 'mm:edit':
            await self.on_manage_menu(query.message)
        elif query.data == 'mm:settings':
            await self.on_settings_menu(query)
        else:
            await self.safe_delete(query.message)
            await self.go_back(query.message)  # fixme: asking lang because query message is bot's message, not user's!
        await query.answer()

    # -------- ADDING ---------

    async def all_nodes_list_maker(self, user_id):
        watch_list = set(await self.storage(user_id).all_nodes_for_user())
        last_nodes = await self.get_all_nodes()
        last_node_texts = [
            # add node_address as a tag
            (self.loc.short_node_desc(n, watching=(n.node_address in watch_list)), n.node_address) for n in last_nodes
        ]
        return TelegramInlineList(last_node_texts, data_proxy=self.data, back_text=self.loc.BUTTON_BACK,
                                  data_prefix='all_nodes').set_extra_buttons_above(
            [
                [
                    InlineKeyboardButton(self.loc.BUTTON_NOP_ADD_ALL_NODES, callback_data='add:all'),
                    InlineKeyboardButton(self.loc.BUTTON_NOP_ADD_ALL_ACTIVE_NODES, callback_data='add:active')
                ]
            ])

    async def on_add_node_menu(self, message: Message):
        await NodeOpStates.ADDING.set()
        tg_list = await self.all_nodes_list_maker(message.chat.id)

        # to hide KB
        # await message.answer(self.loc.TEXT_NOP_ADD_INSTRUCTIONS_PRE, reply_markup=ReplyKeyboardRemove())
        # await message.answer(self.loc.TEXT_NOP_ADD_INSTRUCTIONS, reply_markup=tg_list.reset_page().keyboard())

        await message.edit_text(
            self.loc.TEXT_NOP_ADD_INSTRUCTIONS_PRE + '\n\n' +
            self.loc.TEXT_NOP_ADD_INSTRUCTIONS, reply_markup=tg_list.reset_page().keyboard())

    @message_handler(state=NodeOpStates.ADDING)
    async def on_add_got_message(self, message: Message):
        if message.text == self.loc.BUTTON_BACK:
            await self.show_main_menu(message)
            return

        nodes = await self.parse_nodes_from_text_list(message.text)
        if not nodes:
            await message.answer(self.loc.TEXT_NOP_SEARCH_NO_VARIANTS)
        else:
            variants = join_as_numbered_list(map(self.loc.pretty_node_desc, nodes))
            await message.answer(self.loc.TEXT_NOP_SEARCH_VARIANTS + '\n\n' + variants)

    @query_handler(state=NodeOpStates.ADDING)
    async def on_add_list_callback(self, query: CallbackQuery):
        user_id = query.message.chat.id

        tg_list = await self.all_nodes_list_maker(user_id)
        result = await tg_list.handle_query(query)

        if result.result == result.BACK:
            await self.show_main_menu(query.message, with_welcome=False)
        elif result.result == result.SELECTED:
            node_to_add = result.selected_data_tag

            current_node_set = set(await self.storage(user_id).all_nodes_for_user())
            if node_to_add in current_node_set:
                await self.storage(user_id).remove_user_nodes([node_to_add])
            else:
                await self.add_nodes_for_user(query, [node_to_add], user_id, go_back=False)
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

    async def on_settings_menu(self, query: CallbackQuery):
        loc = self.loc
        await NodeOpStates.SETTINGS.set()
        await query.message.edit_text(loc.TEXT_NOP_SETTINGS_TITLE, reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    self.alert_setting_button(loc.BUTTON_NOP_SETT_SLASHING, NodeOpSetting.SLASH),
                    self.alert_setting_button(loc.BUTTON_NOP_SETT_VERSION,
                                              (NodeOpSetting.VERSION, NodeOpSetting.NEW_VERSION),
                                              data='setting:version'),
                    self.alert_setting_button(loc.BUTTON_NOP_SETT_OFFLINE, NodeOpSetting.OFFLINE),
                ],
                [
                    self.alert_setting_button(loc.BUTTON_NOP_SETT_CHURNING, NodeOpSetting.CHURNING),
                    self.alert_setting_button(loc.BUTTON_NOP_SETT_BOND, NodeOpSetting.BOND),
                    self.alert_setting_button(loc.BUTTON_NOP_SETT_HEIGHT, NodeOpSetting.CHAIN_HEIGHT),
                ],
                [
                    InlineKeyboardButton(self.loc.BUTTON_BACK, callback_data='setting:back')
                ]
            ]
        ))

    @query_handler(state=NodeOpStates.SETTINGS)
    async def on_setting_callback(self, query: CallbackQuery):
        if query.data == 'setting:back':
            await self.show_main_menu(query.message, with_welcome=False)
        elif query.data == NodeOpSetting.SLASH:
            await self.ask_slash_enabled(query)
        elif query.data == 'setting:version':
            await self.ask_new_version_enabled(query)
        elif query.data == NodeOpSetting.BOND:
            await self.ask_bond_enabled(query)
        elif query.data == NodeOpSetting.OFFLINE:
            await self.ask_offline_enabled(query)
        elif query.data == NodeOpSetting.CHAIN_HEIGHT:
            await self.ask_chain_height_enabled(query)
        elif query.data == NodeOpSetting.CHURNING:
            await self.ask_churning_enabled(query)
        await query.answer()

    # -------- SETTINGS : SLASH ---------

    async def ask_slash_enabled(self, query: CallbackQuery):
        is_on = self.is_alert_on(NodeOpSetting.SLASH)
        await self.ask_something_enabled(query, NodeOpStates.SETT_SLASH_ENABLED,
                                         self.loc.text_nop_slash_enabled(is_on),
                                         is_on)

    @query_handler(state=NodeOpStates.SETT_SLASH_ENABLED)
    async def slash_enabled_answer_query(self, query: CallbackQuery):
        await self.handle_query_for_something_on(query,
                                                 NodeOpSetting.SLASH,
                                                 self.ask_slash_threshold,
                                                 self.on_settings_menu)

    async def ask_slash_threshold(self, query: CallbackQuery):
        await NodeOpStates.SETT_SLASH_THRESHOLD.set()
        await query.message.edit_text(self.loc.TEXT_NOP_SLASH_THRESHOLD, reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton('1 pt', callback_data='1'),
                    InlineKeyboardButton('2 pts', callback_data='2'),
                    InlineKeyboardButton('5 pts', callback_data='5'),
                ],
                [
                    InlineKeyboardButton('10 pts', callback_data='10'),
                    InlineKeyboardButton('15 pts', callback_data='15'),
                    InlineKeyboardButton('20 pts', callback_data='20'),
                ],
                [
                    InlineKeyboardButton('50 pts', callback_data='50'),
                    InlineKeyboardButton('100 pts', callback_data='100'),
                    InlineKeyboardButton('200 pts', callback_data='200'),
                ],
                [
                    InlineKeyboardButton(self.loc.BUTTON_BACK, callback_data='back')
                ]
            ]
        ))

    @query_handler(state=NodeOpStates.SETT_SLASH_THRESHOLD)
    async def slash_threshold_answer_query(self, query: CallbackQuery):
        if query.data == 'back':
            await self.on_settings_menu(query)
            await query.answer()
        else:
            threshold = int(query.data)
            self.data[NodeOpSetting.SLASH_THRESHOLD] = threshold
            await self.ask_slash_period(query)
            await query.answer(self.loc.SUCCESS)

    async def ask_slash_period(self, query: CallbackQuery):
        await NodeOpStates.SETT_SLASH_PERIOD.set()
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(self.loc.BUTTON_NOP_2MIN, callback_data='2'),
                    InlineKeyboardButton(self.loc.BUTTON_NOP_5MIN, callback_data='5'),
                    InlineKeyboardButton(self.loc.BUTTON_NOP_15MIN, callback_data='15'),
                    InlineKeyboardButton(self.loc.BUTTON_NOP_30MIN, callback_data='30'),
                    InlineKeyboardButton(self.loc.BUTTON_NOP_60MIN, callback_data='60'),
                ],
                [
                    InlineKeyboardButton(self.loc.BUTTON_BACK, callback_data='back')
                ]
            ]
        )
        text = self.loc.text_nop_ask_slash_period(self.data.get(NodeOpSetting.SLASH_THRESHOLD, 1))
        await query.message.edit_text(text, reply_markup=keyboard)

    @query_handler(state=NodeOpStates.SETT_SLASH_PERIOD)
    async def slash_period_answer_query(self, query: CallbackQuery):
        if query.data == 'back':
            await self.on_settings_menu(query)
            await query.answer()
        else:
            period = int(query.data)
            self.data[NodeOpSetting.SLASH_PERIOD] = MINUTE * period
            await self.on_settings_menu(query)
            await query.answer(self.loc.SUCCESS)

    # -------- SETTINGS : VERSION ---------

    async def ask_new_version_enabled(self, query: CallbackQuery):
        is_on = self.is_alert_on(NodeOpSetting.NEW_VERSION)
        await self.ask_something_enabled(query, NodeOpStates.SETT_NEW_VERSION_ENABLED,
                                         self.loc.text_nop_new_version_enabled(is_on),
                                         is_on)

    @query_handler(state=NodeOpStates.SETT_NEW_VERSION_ENABLED)
    async def new_version_query_handle(self, query: CallbackQuery):
        await self.handle_query_for_something_on(query,
                                                 NodeOpSetting.NEW_VERSION,
                                                 self.ask_version_up_enabled,
                                                 self.ask_version_up_enabled)

    async def ask_version_up_enabled(self, query: CallbackQuery):
        is_on = self.is_alert_on(NodeOpSetting.VERSION)
        await self.ask_something_enabled(query,
                                         NodeOpStates.SETT_UPDATE_VERSION_ENABLED,
                                         self.loc.text_nop_version_up_enabled(is_on),
                                         is_on)

    @query_handler(state=NodeOpStates.SETT_UPDATE_VERSION_ENABLED)
    async def version_up_query_handle(self, query: CallbackQuery):
        await self.handle_query_for_something_on(query,
                                                 NodeOpSetting.VERSION,
                                                 self.on_settings_menu,
                                                 self.on_settings_menu)

    # -------- SETTINGS : BOND ---------

    async def ask_bond_enabled(self, query: CallbackQuery):
        is_on = self.is_alert_on(NodeOpSetting.BOND)
        await self.ask_something_enabled(query, NodeOpStates.SETT_BOND_ENABLED,
                                         self.loc.text_nop_bond_is_enabled(is_on),
                                         is_on)

    @query_handler(state=NodeOpStates.SETT_BOND_ENABLED)
    async def bond_enabled_query_handle(self, query: CallbackQuery):
        await self.handle_query_for_something_on(query,
                                                 NodeOpSetting.BOND,
                                                 self.on_settings_menu,
                                                 self.on_settings_menu)

    # -------- SETTINGS : OFFLINE ---------

    async def ask_offline_enabled(self, query: CallbackQuery):
        is_on = self.is_alert_on(NodeOpSetting.OFFLINE)
        await self.ask_something_enabled(query, NodeOpStates.SETT_OFFLINE_ENABLED,
                                         self.loc.text_nop_offline_enabled(is_on),
                                         is_on)

    @query_handler(state=NodeOpStates.SETT_OFFLINE_ENABLED)
    async def offline_enabled_query_handle(self, query: CallbackQuery):
        await self.handle_query_for_something_on(query,
                                                 NodeOpSetting.OFFLINE,
                                                 self.on_settings_menu,
                                                 self.on_settings_menu)

    # -------- SETTINGS : CHAIN HEIGHT ---------

    async def ask_chain_height_enabled(self, query: CallbackQuery):
        is_on = self.is_alert_on(NodeOpSetting.CHAIN_HEIGHT)
        await self.ask_something_enabled(query, NodeOpStates.SETT_HEIGHT_ENABLED,
                                         self.loc.text_nop_chain_height_enabled(is_on),
                                         is_on)

    @query_handler(state=NodeOpStates.SETT_HEIGHT_ENABLED)
    async def chain_height_enabled_query_handle(self, query: CallbackQuery):
        await self.handle_query_for_something_on(query,
                                                 NodeOpSetting.CHAIN_HEIGHT,
                                                 self.ask_block_lag_time,
                                                 self.on_settings_menu)

    async def ask_block_lag_time(self, query: CallbackQuery):
        await NodeOpStates.SETT_HEIGHT_LAG_TIME.set()
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(self.loc.BUTTON_NOP_2MIN, callback_data='2'),
                    InlineKeyboardButton(self.loc.BUTTON_NOP_5MIN, callback_data='5'),
                    InlineKeyboardButton(self.loc.BUTTON_NOP_15MIN, callback_data='15'),
                    InlineKeyboardButton(self.loc.BUTTON_NOP_30MIN, callback_data='30'),
                    InlineKeyboardButton(self.loc.BUTTON_NOP_60MIN, callback_data='60'),
                ],
                [
                    InlineKeyboardButton(self.loc.BUTTON_BACK, callback_data='back')
                ]
            ]
        )
        text = self.loc.text_nop_ask_chain_height_lag_time(self.data.get(NodeOpSetting.CHAIN_HEIGHT_INTERVAL, 1))
        await query.message.edit_text(text, reply_markup=keyboard)

    @query_handler(state=NodeOpStates.SETT_HEIGHT_LAG_TIME)
    async def block_height_lag_time_answer_query(self, query: CallbackQuery):
        if query.data == 'back':
            await self.on_settings_menu(query)
            await query.answer()
        else:
            period = int(query.data)
            self.data[NodeOpSetting.CHAIN_HEIGHT_INTERVAL] = MINUTE * period
            await self.on_settings_menu(query)
            await query.answer(self.loc.SUCCESS)

    # -------- SETTINGS : CHURNING ---------

    async def ask_churning_enabled(self, query: CallbackQuery):
        is_on = self.is_alert_on(NodeOpSetting.CHURNING)
        await self.ask_something_enabled(query, NodeOpStates.SETT_CHURNING_ENABLED,
                                         self.loc.text_nop_churning_enabled(is_on),
                                         is_on)

    @query_handler(state=NodeOpStates.SETT_CHURNING_ENABLED)
    async def churning_enabled_query_handle(self, query: CallbackQuery):
        await self.handle_query_for_something_on(query,
                                                 NodeOpSetting.CHURNING,
                                                 self.on_settings_menu,
                                                 self.on_settings_menu)

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

    def is_alert_on(self, name):
        return bool(self.data.get(name, True))

    def alert_setting_button(self, orig, setting, data=None):
        data = data or setting
        if isinstance(setting, (list, tuple)):
            is_on = any(self.is_alert_on(s) for s in setting)
        else:
            is_on = self.is_alert_on(setting)
        return InlineKeyboardButton(orig + (f' ✔' if is_on else ''), callback_data=data)

    async def ask_something_enabled(self, query: CallbackQuery, state: State, text: str, is_on: bool):
        await state.set()
        loc = self.loc
        await query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(loc.BUTTON_NOP_LEAVE_ON if is_on else loc.BUTTON_NOP_TURN_ON,
                                         callback_data='on'),
                    InlineKeyboardButton(loc.BUTTON_NOP_LEAVE_OFF if not is_on else loc.BUTTON_NOP_TURN_OFF,
                                         callback_data='off')
                ],
                [InlineKeyboardButton(loc.BUTTON_BACK, callback_data='back')]
            ]))

    async def handle_query_for_something_on(self, query: CallbackQuery, setting, next_on_func, next_off_func):
        if query.data == 'back':
            await self.on_settings_menu(query)
        elif query.data == 'on':
            self.data[setting] = True
            await next_on_func(query)
        elif query.data == 'off':
            self.data[setting] = False
            await next_off_func(query)
        await query.answer()
