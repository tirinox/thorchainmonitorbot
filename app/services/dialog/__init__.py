from aiogram.types import ContentTypes, Message

from services.dialog.main_menu import MainMenuDialog
from services.dialog.stake_info import StakeDialog
from services.lib.depcont import DepContainer


async def sticker_handler(message: Message):
    s = message.sticker
    await message.reply(f'Sticker: {s.emoji}: {s.file_id}')


def init_dialogs(d: DepContainer):
    MainMenuDialog.register(d)
    StakeDialog.back_dialog = MainMenuDialog
    StakeDialog.back_func = MainMenuDialog.entry_point
    StakeDialog.register(d)
    d.dp.register_message_handler(sticker_handler, content_types=ContentTypes.STICKER, state='*')
