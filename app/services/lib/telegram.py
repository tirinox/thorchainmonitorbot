import math
import typing
import urllib.parse

import aiohttp
from aiogram.dispatcher.storage import FSMContextProxy
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message

TG_TEST_USER = 192398802


def to_json_bool(b):
    return 'true' if b else 'false'


async def telegram_send_message_basic(bot_token, user_id, message_text: str,
                                      disable_web_page_preview=True,
                                      disable_notification=True):
    message_text = message_text.strip()

    if not message_text:
        return

    message_text = urllib.parse.quote_plus(message_text)
    url = (
        f"https://api.telegram.org/"
        f"bot{bot_token}/sendMessage?"
        f"chat_id={user_id}&"
        f"text={message_text}&"
        f"parse_mode=HTML&"
        f"disable_web_page_preview={to_json_bool(disable_web_page_preview)}&"
        f"disable_notification={to_json_bool(disable_notification)}"
    )

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                err = await resp.read()
                raise Exception(f'Telegram error: "{err}"')
            return resp.status == 200


class InlineListResult(typing.NamedTuple):
    NOT_HANDLED = ''
    BACK = 'back'
    PREV_PAGE = 'prev'
    NEXT_PAGE = 'next'
    SELECTED = 'selected'
    result: str = NOT_HANDLED
    selected_item: object = None
    selected_item_index: int = 0
    selected_data_tag: str = ''


class TelegramInlineList:
    def __init__(self, items,
                 data_proxy: FSMContextProxy,
                 max_rows=3, max_columns=2,
                 back_text='Back',
                 prev_page_text='«',
                 next_page_text='»',
                 data_prefix='list'):
        assert isinstance(items, (list, tuple))
        self._items = items
        self._data = data_proxy
        self.back_text = back_text
        self.prev_page_text = prev_page_text
        self.next_page_text = next_page_text
        self._max_columns = max_columns
        self._max_rows = max_rows
        self._n = len(items)
        self._per_page = max_rows * max_columns
        self._total_pages = int(math.ceil(self._n / self._per_page))
        self.data_prefix = data_prefix
        self.extra_buttons_above = []
        self.extra_buttons_below = []

    def get_item_display_text(self, index):
        item = self._items[index]
        if isinstance(item, tuple):
            display_text, _ = item
            return display_text
        else:
            return item

    def get_item_data_tag(self, index):
        item = self._items[index]
        if isinstance(item, tuple):
            _, data_tag = item
            return data_tag
        else:
            return item

    def set_extra_buttons_above(self, extra_buttons):
        self.extra_buttons_above = extra_buttons
        return self

    def set_extra_buttons_below(self, extra_buttons):
        self.extra_buttons_below = extra_buttons
        return self

    def keyboard(self):
        inline_kbd = []
        if self.extra_buttons_above:
            inline_kbd += self.extra_buttons_above

        current_page = self.current_page

        offset = current_page * self._per_page

        for rows in range(self._max_rows):
            row = []
            for column in range(self._max_columns):
                if offset == self._n:
                    break
                counter = offset + 1
                text = self.get_item_display_text(offset)
                row.append(
                    InlineKeyboardButton(
                        f'{counter}. {text}',
                        callback_data=f'{self.data_prefix}:{offset}'
                    )
                )
                offset += 1

            inline_kbd.append(row)
            if offset == self._n:
                break

        last_row = [
            InlineKeyboardButton(
                self.back_text,
                callback_data=f'{self.data_prefix}:{InlineListResult.BACK}'
            )
        ]

        if current_page > 0:
            last_row.append(InlineKeyboardButton(
                self.prev_page_text,
                callback_data=f'{self.data_prefix}:{InlineListResult.PREV_PAGE}')
            )

        if current_page < self._total_pages - 1:
            last_row.append(InlineKeyboardButton(
                self.next_page_text,
                callback_data=f'{self.data_prefix}:{InlineListResult.NEXT_PAGE}'))

        inline_kbd.append(last_row)

        if self.extra_buttons_below:
            inline_kbd += self.extra_buttons_below

        return InlineKeyboardMarkup(inline_keyboard=inline_kbd)

    @property
    def current_page(self):
        return int(self._data.get(self.data_page_key, 0))

    @property
    def data_page_key(self):
        return f"{self.data_prefix}:page"

    def reset_page(self):
        self._data[self.data_page_key] = 0
        return self

    async def _flip_keyboard_page(self, message: Message, forward=True):
        old_page = self.current_page
        if forward:
            new_page = min(self._total_pages - 1, old_page + 1)
        else:
            new_page = max(0, old_page - 1)

        if old_page != new_page:
            self._data[self.data_page_key] = new_page
            await message.edit_reply_markup(self.keyboard())

    @staticmethod
    async def clear_keyboard(query: CallbackQuery):
        await query.message.edit_reply_markup(reply_markup=None)

    def __len__(self):
        return len(self._items)

    async def handle_query(self, query: CallbackQuery) -> InlineListResult:
        ILR = InlineListResult
        data = query.data
        if not data.startswith(self.data_prefix):
            return ILR(ILR.NOT_HANDLED)

        try:
            action = data.split(':')[1]
        except (IndexError, AttributeError):
            return ILR(ILR.NOT_HANDLED)
        if action == ILR.BACK:
            await self.clear_keyboard(query)
            return ILR(ILR.BACK)
        elif action == ILR.PREV_PAGE:
            await self._flip_keyboard_page(query.message, forward=False)
            return ILR(ILR.PREV_PAGE)
        elif action == ILR.NEXT_PAGE:
            await self._flip_keyboard_page(query.message, forward=True)
            return ILR(ILR.NEXT_PAGE)
        else:
            try:
                item_index = int(action)
                assert 0 <= item_index < self._n
            except (ValueError, AssertionError):
                return ILR(ILR.NOT_HANDLED)
            else:
                text = self.get_item_display_text(item_index)
                data_tag = self.get_item_data_tag(item_index)
                return ILR(ILR.SELECTED,
                           selected_item=text,
                           selected_item_index=item_index,
                           selected_data_tag=data_tag)
