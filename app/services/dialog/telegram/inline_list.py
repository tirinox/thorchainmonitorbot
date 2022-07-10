import math
import typing

from aiogram.dispatcher.storage import FSMContextProxy
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery


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
                 max_rows=2, max_columns=2,
                 back_text='Back',
                 prev_page_text='«',
                 next_page_text='»',
                 data_prefix='list',
                 loc=None):
        assert isinstance(items, (list, tuple))
        self._items = items
        self._data = data_proxy
        self.back_text = back_text
        self.prev_page_text = loc.LIST_PREV_PAGE if loc else prev_page_text
        self.next_page_text = loc.LIST_NEXT_PAGE if loc else next_page_text
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
                if offset >= self._n:
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

        last_row = []

        if self.back_text:
            last_row.append(InlineKeyboardButton(self.back_text, callback_data=self.data_back))

        if self._n:
            if current_page > 0:
                last_row.append(InlineKeyboardButton(
                    self.prev_page_text,
                    callback_data=f'{self.data_prefix}:{InlineListResult.PREV_PAGE}')
                )

            if current_page < self._total_pages - 1:
                last_row.append(InlineKeyboardButton(
                    self.next_page_text,
                    callback_data=f'{self.data_prefix}:{InlineListResult.NEXT_PAGE}')
                )

        if last_row:
            inline_kbd.append(last_row)

        if self.extra_buttons_below:
            inline_kbd += self.extra_buttons_below

        return InlineKeyboardMarkup(inline_keyboard=inline_kbd)

    @property
    def current_page(self):
        page = int(self._data.get(self.data_page_key, 0))
        return max(0, min(page, self._total_pages - 1))

    @property
    def data_page_key(self):
        return f"{self.data_prefix}:page"

    @property
    def data_back(self):
        return f'{self.data_prefix}:{InlineListResult.BACK}'

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
            await query.answer()
            return ILR(ILR.BACK)
        elif action == ILR.PREV_PAGE:
            await self._flip_keyboard_page(query.message, forward=False)
            await query.answer()
            return ILR(ILR.PREV_PAGE)
        elif action == ILR.NEXT_PAGE:
            await self._flip_keyboard_page(query.message, forward=True)
            await query.answer()
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

    def __eq__(self, other: 'TelegramInlineList'):
        if other is self:
            return True
        if other.current_page != self.current_page:
            return False

        current_page = self.current_page
        offset = current_page * self._per_page

        for rows in range(self._max_rows):
            for column in range(self._max_columns):
                if offset == self._n:
                    break
                text = self.get_item_display_text(offset)
                other_text = other.get_item_display_text(offset)
                if text != other_text:
                    return False
                offset += 1
            if offset == self._n:
                break
        return True
