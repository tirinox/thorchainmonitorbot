import asyncio
from io import BytesIO
from typing import Optional

from discord import Client, File
from markdownify import markdownify

from services.lib.config import Config
from services.lib.draw_utils import img_to_bio
from services.notify.channel import MessageType, BoardMessage
from services.lib.utils import class_logger


class DiscordBot:
    async def on_ready(self):
        self.logger.info('ready')

    async def on_message(self, message):
        self.logger.info(repr(message))

    def __init__(self, cfg: Config, sticker_downloader):
        self.client = Client()
        self.client.event(self.on_ready)
        self.client.event(self.on_message)
        self.logger = class_logger(self)
        self._token = cfg.as_str('discord.bot.token')
        self._sticker_downloader = sticker_downloader

    def start_in_background(self):
        asyncio.create_task(self.client.start(self._token))

    @staticmethod
    def convert_text_to_discord_formatting(text):
        text = text.replace('<pre>', '<code>')
        text = text.replace('</pre>', '</code>')
        return markdownify(text)

    async def send_message_to_channel(self, channel, text: Optional[str], picture=None, pic_name='pic.png',
                                      need_convert=False):
        if not channel or not text:
            self.logger.warning('no data to send')
            return

        if need_convert:
            text = self.convert_text_to_discord_formatting(text)

        if picture:
            if not isinstance(picture, BytesIO):
                picture = img_to_bio(picture, pic_name)

            picture.seek(0)
            file = File(picture)
        else:
            file = None

        channel = self.client.get_channel(channel)
        await channel.send(text, file=file)

    async def safe_send_message(self, chat_id, msg: BoardMessage, **kwargs) -> bool:
        try:
            if msg.message_type == MessageType.TEXT:
                await self.send_message_to_channel(chat_id, msg.text, need_convert=True)
            elif msg.message_type == MessageType.STICKER:
                sticker = await self._sticker_downloader.get_sticker_image(msg.text)
                await self.send_message_to_channel(chat_id, ' ', picture=sticker)
            elif msg.message_type == MessageType.PHOTO:
                await self.send_message_to_channel(chat_id, msg.text, picture=msg.photo, need_convert=True)
            return True
        except Exception as e:
            self.logger.exception(f'discord exception {e}, {msg.message_type = }, text = "{msg.text}"!')
            return False
