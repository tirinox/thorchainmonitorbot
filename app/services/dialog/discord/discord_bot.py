import asyncio
from typing import Optional

from discord import Client, File, Intents
from markdownify import markdownify

from services.lib.config import Config
from services.lib.utils import WithLogger
from services.notify.channel import MessageType, BoardMessage


class DiscordBot(WithLogger):
    async def on_ready(self):
        self.logger.info('ready')

    async def on_message(self, message):
        self.logger.info(repr(message))

    def __init__(self, cfg: Config, sticker_downloader):
        super().__init__()
        intents = Intents.default()
        intents.typing = False

        self.client = Client(intents=intents)
        self.client.event(self.on_ready)
        self.client.event(self.on_message)

        self._token = cfg.as_str('discord.bot.token')
        self._sticker_downloader = sticker_downloader

    def start_in_background(self):
        asyncio.create_task(self.client.start(self._token))

    @staticmethod
    def convert_text_to_discord_formatting(text):
        text = text.replace('<pre>', '<code>')
        text = text.replace('</pre>', '</code>')
        return markdownify(text)

    async def send_message_to_channel(self, channel, text: Optional[str], pic_bio=None,
                                      need_convert=False):
        if not channel or not text:
            self.logger.warning('no data to send')
            return

        if need_convert:
            text = self.convert_text_to_discord_formatting(text)

        file = File(pic_bio) if pic_bio else None

        # int(channel) is important! otherwise it will fail
        channel = self.client.get_channel(int(channel))
        result = await channel.send(text, file=file, suppress_embeds=True)
        self.logger.info(f'Result: {result}')

    async def send_message(self, chat_id, msg: BoardMessage, **kwargs) -> bool:
        try:
            if msg.message_type == MessageType.TEXT:
                await self.send_message_to_channel(chat_id, msg.text, need_convert=True)
            elif msg.message_type == MessageType.STICKER:
                sticker_bio = await self._sticker_downloader.get_sticker_image_bio(msg.text)
                await self.send_message_to_channel(chat_id, ' ', pic_bio=sticker_bio)
            elif msg.message_type == MessageType.PHOTO:
                pic_bio = msg.get_bio()
                await self.send_message_to_channel(chat_id, msg.text, pic_bio=pic_bio, need_convert=True)
            return True
        except Exception as e:
            self.logger.exception(f'discord exception {e}, {msg.message_type = }, text = "{msg.text}"!')
            return False
