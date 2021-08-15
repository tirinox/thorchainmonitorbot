from aiogram.types import ContentTypes, Message

from services.dialog.avatar_picture_dialog import AvatarDialog
from services.dialog.inline_bot_handler import InlineBotHandlerDialog
from services.dialog.main_menu import MainMenuDialog
from services.dialog.metrics_menu import MetricsDialog
from services.dialog.settings_menu import SettingsDialog
from services.dialog.lp_info_dialog import LiquidityInfoDialog
from services.lib.depcont import DepContainer
from services.dialog.node_op_menu import NodeOpDialog

async def sticker_handler(message: Message):
    s = message.sticker
    await message.reply(f'Sticker: {s.emoji}: {s.file_id}')


def init_dialogs(d: DepContainer):
    MainMenuDialog.register(d)

    mm = MainMenuDialog
    LiquidityInfoDialog.register(d, mm, mm.entry_point)
    SettingsDialog.register(d, mm, mm.entry_point)
    MetricsDialog.register(d, mm, mm.entry_point)
    AvatarDialog.register(d, mm, mm.entry_point)
    InlineBotHandlerDialog.register(d, mm, mm.entry_point)
    NodeOpDialog.register(d, mm, mm.entry_point)

    d.dp.register_message_handler(sticker_handler, content_types=ContentTypes.STICKER, state='*')
