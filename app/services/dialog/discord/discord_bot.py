import asyncio
from io import BytesIO

from discord import Client, File

from services.lib.config import Config
from services.lib.draw_utils import img_to_bio
from services.lib.utils import class_logger


class DiscordBot:
    async def on_ready(self):
        self.logger.info('ready')

    async def on_message(self, message):
        self.logger.info(repr(message))

    def __init__(self, cfg: Config):
        self.client = Client()
        self.client.event(self.on_ready)
        self.client.event(self.on_message)
        self.logger = class_logger(self)
        self._token = cfg.as_str('discord.bot.token')

    def start_in_background(self):
        asyncio.create_task(self.client.start(self._token))

    async def send_message_to_channel(self, channel, text, picture=None, pic_name='pic.png'):
        if not channel or not text:
            self.logger.warning('no data to send')
            return

        if picture:
            if not isinstance(picture, BytesIO):
                picture = img_to_bio(picture, pic_name)
            file = File(picture)
        else:
            file = None

        channel = self.client.get_channel(channel)
        await channel.send(text, file=file)
