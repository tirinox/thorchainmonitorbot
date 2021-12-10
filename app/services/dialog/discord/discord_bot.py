import asyncio

from discord import Client

from services.lib.config import Config
from services.lib.utils import class_logger


class DiscordBot:
    async def on_ready(self):
        print('ready')

    async def on_message(self, message):
        print('discord: ', message)

    def __init__(self, cfg: Config):
        self.client = Client()
        self.client.event(self.on_ready)
        self.client.event(self.on_message)
        self.logger = class_logger(self)
        self._token = cfg.as_str('discord.bot.token')

        self._channels = cfg.get_pure('discord.channels')
        print(self._channels)

    def start_in_background(self):
        asyncio.create_task(self.client.start(self._token))
