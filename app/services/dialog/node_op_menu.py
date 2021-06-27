from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.types import Message
from aiogram.utils.helper import HelperMode

from services.dialog.base import BaseDialog, message_handler


class NodeOpStates(StatesGroup):
    mode = HelperMode.snake_case
    MAIN = State()


class NodeOpDialog(BaseDialog):
    @message_handler(state=NodeOpStates.MAIN)
    async def on_enter(self, message: Message):
        ...
