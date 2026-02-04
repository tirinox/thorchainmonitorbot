import logging

from aiogram.types import ContentTypes, Message

from .admin_menu import AdminDialog
from .avatar_picture_dialog import AvatarDialog
from .main_menu import MainMenuDialog
from .metrics_menu import MetricsDialog
from .my_wallets_menu import MyWalletsMenu
from .node_op_menu import NodeOpDialog
from .settings_menu import SettingsDialog
from lib.depcont import DepContainer


async def sticker_handler(message: Message):
    s = message.sticker
    await message.reply(f'Sticker: {s.emoji}: {s.file_id}')


async def unhandled_handler(message: Message):
    logging.warning(f'Unhandled message = {message}')
    await message.reply('💁‍♀️ <b>Sorry.</b> Your message could not be handled in the current bot state. '
                        'Please run 🤜 /start 🤛 command to restart the bot.', disable_notification=True)


def init_dialogs(d: DepContainer):
    MainMenuDialog.register(d)

    mm = MainMenuDialog
    MyWalletsMenu.register(d, mm, mm.entry_point)
    SettingsDialog.register(d, mm, mm.entry_point)
    MetricsDialog.register(d, mm, mm.entry_point)
    AvatarDialog.register(d, mm, mm.entry_point)
    AdminDialog.register(d, mm, mm.entry_point)

    if NodeOpDialog.is_enabled(d.cfg):
        logging.info('NodeOpDialog is enabled.')
        NodeOpDialog.register(d, mm, mm.entry_point)

    d.telegram_bot.dp.register_message_handler(sticker_handler, content_types=ContentTypes.STICKER, state='*')
    d.telegram_bot.dp.register_message_handler(unhandled_handler, content_types=ContentTypes.TEXT, state='*')
