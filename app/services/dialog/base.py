import logging
import secrets
from abc import ABC
from functools import wraps
from typing import Optional

from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.dispatcher.storage import FSMContextProxy, FSMContext
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove, InlineQuery
from aiogram.utils.exceptions import MessageCantBeDeleted, MessageToEditNotFound, MessageToDeleteNotFound

from localization import BaseLocalization
from localization.base import CREATOR_TG
from services.lib.depcont import DepContainer
from services.lib.texts import code

logger = logging.getLogger('DIALOGS')


async def display_error(message: Message, e: Exception):
    tag = secrets.token_hex(8)
    logger.exception(f"TAG: {tag}")
    await message.answer(code(f"Sorry! An error occurred: {str(e)}. Incident ID is {tag}.") +
                         f"\nFeedback/support: {CREATOR_TG}.")


def bot_query_error_guard(func):
    @wraps(func)
    async def wrapper(query: CallbackQuery, *args, **kwargs):
        try:
            return await func(query, *args, **kwargs)
        except Exception as e:
            await display_error(query.message, e)

    return wrapper


def bot_error_guard(func):
    @wraps(func)
    async def wrapper(message: Message, *args, **kwargs):
        try:
            return await func(message, *args, **kwargs)
        except Exception as e:
            await display_error(message, e)

    return wrapper


def message_handler(*custom_filters, commands=None, regexp=None, content_types=None, state=None):
    def outer(f):
        f.handler_stuff = {
            'custom_filters': custom_filters,
            'commands': commands.split(',') if isinstance(commands, str) else commands,
            'regexp': regexp,
            'content_types': content_types,
            'state': state,
        }
        return f

    return outer


def query_handler(*custom_filters, state=None):
    def outer(f):
        f.query_stuff = {
            'custom_filters': custom_filters,
            'state': state,
        }
        return f

    return outer


def inline_bot_handler(*custom_filters):
    def outer(f):
        f.inline_bot_stuff = {
            'custom_filters': custom_filters
        }
        return f

    return outer


class BaseDialog(ABC):
    back_dialog: 'BaseDialog' = None
    back_func = None

    class States(StatesGroup):
        DUMMY = State()

    def __init__(self, loc: BaseLocalization, data: Optional[FSMContextProxy], d: DepContainer):
        self.deps = d
        self.loc = loc
        self.data = data

    @classmethod
    def register(cls, d: DepContainer, back_dialog=None, back_func=None):
        cls.back_dialog = back_dialog
        cls.back_func = back_func

        members = cls.__dict__.items()
        # go through all annotated methods and register them as bot dispatcher's handlers
        for name, f in members:
            if hasattr(f, 'handler_stuff'):
                cls.register_handler(d, f, name)
            elif hasattr(f, 'query_stuff'):
                cls.register_query_handler(d, f, name)
            elif hasattr(f, 'inline_bot_stuff'):
                cls.register_inline_bot_handler(d, f, name)

    @classmethod
    def register_query_handler(cls, d: DepContainer, f, name):
        query_stuff = f.query_stuff

        @d.dp.callback_query_handler(*query_stuff['custom_filters'], state=query_stuff['state'])
        @bot_query_error_guard
        async def handler(query: CallbackQuery, state: FSMContext, that_name=name):  # name=name important!!
            logger.info({
                'from': (query.from_user.id, query.from_user.first_name, query.from_user.username),
                'data': query.data
            })
            async with state.proxy() as data:
                loc = await d.loc_man.get_from_db(query.from_user.id, d.db)
                handler_class = cls(loc, data, d)
                handler_method = getattr(handler_class, that_name)
                return await handler_method(query)

    @classmethod
    def register_inline_bot_handler(cls, d: DepContainer, f, name):
        inline_bot_stuff = f.inline_bot_stuff

        @d.dp.inline_handler(*inline_bot_stuff['custom_filters'], state='*')
        async def handler(inline_query: InlineQuery, that_name=name):  # name=name important!!
            try:
                logger.info({
                    'from': (inline_query.from_user.id,
                             inline_query.from_user.username,
                             inline_query.from_user.first_name),
                    'query': inline_query.query
                })

                loc = d.loc_man.default
                handler_class = cls(loc, None, d)
                handler_method = getattr(handler_class, that_name)
                return await handler_method(inline_query)
            except Exception as e:
                logger.exception('Inline bot query exception!')

    @classmethod
    def register_handler(cls, d, f, name):
        handler_stuff = f.handler_stuff

        @d.dp.message_handler(*handler_stuff['custom_filters'],
                              commands=handler_stuff['commands'],
                              state=handler_stuff['state'],
                              regexp=handler_stuff['regexp'],
                              content_types=handler_stuff['content_types'])
        @bot_error_guard
        async def handler(message: Message, state: FSMContext, that_name=name):  # name=name important!!
            logger.info({
                'from': (message.from_user.id, message.from_user.first_name, message.from_user.username),
                'text': message.text
            })
            async with state.proxy() as data:
                loc = await d.loc_man.get_from_db(message.from_user.id, d.db)
                handler_class = cls(loc, data, d)
                handler_method = getattr(handler_class, that_name)
                return await handler_method(message)

    # noinspection PyCallingNonCallable
    async def go_back(self, message: Message):
        message.text = ''
        obj = self.back_dialog(self.loc, self.data, self.deps)
        func = getattr(obj, self.back_func.__name__)
        await func(message)

    @staticmethod
    async def safe_delete(message: Message):
        try:
            await message.delete()
        except (MessageCantBeDeleted, MessageToEditNotFound, MessageToDeleteNotFound):
            logger.warning('can not delete message')
            pass

    @property
    def loading_sticker(self):
        return self.deps.cfg.as_str('telegram.common.loading_sticker', default=None)

    async def answer_loading_sticker(self, message: Message, silent=True, remove_keyboard=False) -> Message:
        return await message.answer_sticker(self.loading_sticker, disable_notification=silent,
                                            reply_markup=ReplyKeyboardRemove() if remove_keyboard else None)
