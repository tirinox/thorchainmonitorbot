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
        self.client = SocketModeClient(
            # This app-level token will be used only for establishing a connection
            app_token=cfg.as_str('slack.bot.app_token'),  # xapp-A111-222-xyz
            # You will be using this WebClient for performing Web API calls in listeners
            web_client=AsyncWebClient(token=cfg.as_str('slack.bot.bot_token'))  # xoxb-111-222-xyz
        )
        # noinspection PyTypeChecker
        self.client.socket_mode_request_listeners.append(self._process)

    async def _process(self, client: SocketModeClient, req: SocketModeRequest):
        ...

    def start_in_background(self):
        asyncio.create_task(self.client.connect())

    async def send_message_to_channel(self, channel, text: Optional[str], picture=None, pic_name='pic.png',
                                      need_convert=True):
        if need_convert:
            text = markdownify(text)

        if picture:
            if not isinstance(picture, BytesIO):
                picture = img_to_bio(picture, pic_name)

            response = await self.client.web_client.files_upload(
                file=picture,
                initial_comment=text,
                channel=channel,
            )
        else:
            response = await self.client.web_client.chat_postMessage(channel=channel,
                                                                     text=text)

        self.logger.info(f'Slack: {response.data}')
