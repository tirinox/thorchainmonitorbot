import logging

from aiogram.types import ContentTypes, Message

from services.dialog.avatar_picture_dialog import AvatarDialog
from services.dialog.inline_bot_handler import InlineBotHandlerDialog
from services.dialog.main_menu import MainMenuDialog
from services.dialog.metrics_menu import MetricsDialog
from services.dialog.settings_menu import SettingsDialog
from services.dialog.lp_info_dialog import MyWalletsMenu
from services.lib.depcont import DepContainer
from services.dialog.node_op_menu import NodeOpDialog


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

    if InlineBotHandlerDialog.is_enabled(d.cfg):
        logging.info('InlineBotHandlerDialog is enabled.')
        InlineBotHandlerDialog.register(d, mm, mm.entry_point)

    if NodeOpDialog.is_enabled(d.cfg):
        logging.info('NodeOpDialog is enabled.')
        NodeOpDialog.register(d, mm, mm.entry_point)

    d.telegram_bot.dp.register_message_handler(sticker_handler, content_types=ContentTypes.STICKER, state='*')
    d.telegram_bot.dp.register_message_handler(unhandled_handler, content_types=ContentTypes.TEXT, state='*')
