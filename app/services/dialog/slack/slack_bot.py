import asyncio
from io import BytesIO
from typing import Optional

from markdownify import markdownify
from slack_sdk.socket_mode.aiohttp import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.web.async_client import AsyncWebClient

from services.lib.config import Config
from services.lib.draw_utils import img_to_bio
from services.lib.utils import class_logger


class SlackBot:
    def __init__(self, cfg: Config):
        self.logger = class_logger(self)

    async def _process(self, client: SocketModeClient, req: SocketModeRequest):
        ...

    def start_in_background(self):
        ...

    async def send_message_to_channel(self, channel, text: Optional[str], picture=None, pic_name='pic.png',
                                      need_convert=True):
        ...
