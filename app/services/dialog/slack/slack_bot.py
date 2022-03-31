from io import BytesIO
from typing import Optional

import slack_sdk.errors
from htmlslacker import HTMLSlacker
from slack_bolt.adapter.starlette.async_handler import AsyncSlackRequestHandler
from slack_bolt.async_app import AsyncApp
from slack_bolt.oauth.async_oauth_settings import AsyncOAuthSettings
from slack_sdk.oauth.installation_store import FileInstallationStore
from slack_sdk.oauth.state_store import FileOAuthStateStore

from localization import LocalizationManager, BaseLocalization
from services.lib.config import Config
from services.lib.constants import Messengers
from services.lib.db import DB
from services.lib.draw_utils import img_to_bio
from services.lib.nop_links import SettingsManager
from services.lib.texts import CHANNEL_INACTIVE
from services.lib.utils import class_logger


# example: https://github.com/slackapi/bolt-python/blob/main/examples/starlette/async_oauth_app.py


class SlackBot:
    INSTALLATION_DIR = "./data/slack_db/installations"
    STATE_DIR = "./data/slack_db/states"
    SCOPES = [
        'commands',
        'im:history',
        'channels:read',
        'chat:write',
        'files:write',
    ]
    REASONS_TO_STOP_NOTIFICATIONS = ('not_in_channel', 'invalid_auth')

    def __init__(self, cfg: Config, db: DB):
        self.logger = class_logger(self)
        self.db = db
        self.cfg = cfg

        slack_client_id = cfg.as_str('slack.bot.client_id')
        slack_client_secret = cfg.as_str('slack.bot.client_secret')
        oauth_settings = AsyncOAuthSettings(
            client_id=slack_client_id,
            client_secret=slack_client_secret,
            scopes=self.SCOPES,
            installation_store=FileInstallationStore(base_dir=self.INSTALLATION_DIR),
            state_store=FileOAuthStateStore(expiration_seconds=600, base_dir=self.STATE_DIR),
        )

        self.slack_app = AsyncApp(
            signing_secret=cfg.as_str('slack.bot.singing_secret'),
            oauth_settings=oauth_settings,
            token=cfg.as_str('slack.bot.bot_token')
        )
        self.slack_handler = AsyncSlackRequestHandler(self.slack_app)
        self.setup_commands()

        self._settings_manager = SettingsManager(db, cfg)

    def get_localization(self, channel) -> BaseLocalization:
        return LocalizationManager(self.cfg).default

    async def send_message_to_channel(self, channel, text: Optional[str] = '', picture=None, pic_name='pic.png',
                                      need_convert=True, file_type='png'):
        if need_convert:
            text = self.convert_html_to_my_format(text)

        try:
            if picture:
                if not isinstance(picture, BytesIO):
                    picture = img_to_bio(picture, pic_name)
                else:
                    picture = picture.read()

                response = await self.slack_app.client.files_upload(
                    file=picture,
                    initial_comment=text,
                    channels=[channel],
                    filetype=file_type,
                )
            else:
                response = await self.slack_app.client.chat_postMessage(
                    channel=channel,
                    text=text,
                    mrkdwn=True,
                    unfurl_links=False
                )

            self.logger.debug(f'Slack response: {response.data}')
            return True
        except slack_sdk.errors.SlackApiError as e:
            self.logger.error(f'Slack error: {e}')
            error = e.response['error']
            if error in self.REASONS_TO_STOP_NOTIFICATIONS:
                return CHANNEL_INACTIVE
            return error

    def _context(self, channel_id):
        return self._settings_manager.get_context(channel_id)

    @staticmethod
    def _infer_channel_name(body: dict):
        chan_name = body['channel_name']
        user_name = body['user_name']
        if chan_name == 'directmessage':
            return f'DM:<@{user_name}>'
        else:
            return f'#{chan_name}'

    async def _pause_unpause(self, body, ack, say, pause):
        channel_id = body["channel_id"]

        async with self._context(channel_id) as settings:
            if not settings:
                await ack(self.get_localization(channel_id).TEXT_NOP_NEED_SETUP_SLACK)
                return

            await ack()

            prev_paused = settings.is_paused
            if pause:
                settings.pause()
            else:
                settings.unpause()

            channel_name = self._infer_channel_name(body)
            text = self.get_localization(channel_id).text_nop_paused_slack(pause, prev_paused, channel_name)
            await say(text)

    def setup_commands(self):
        app = self.slack_app

        # @app.shortcut("nop_settings")
        @app.command("/settings")
        async def settings_command(ack, body):
            channel_id = body.get('channel_id')
            async with self._context(channel_id) as settings:
                token = await self._settings_manager.generate_new_token(channel_id)

                self._settings_manager.set_messenger_data(
                    settings,
                    platform=Messengers.SLACK,
                    username=body.get('user_name', 'user'),
                    channel_name=body.get('channel_name', '-'),
                )

                url = self._settings_manager.get_link(token)

                channel_name = self._infer_channel_name(body)
                text = self.get_localization(channel_id).text_nop_settings_link_slack(url, channel_name)
                await ack(text)

        # @app.shortcut("nop_pause")
        @app.command("/pause")
        async def pause_command(ack, body, say):
            await self._pause_unpause(body, ack, say, pause=True)

        # @app.shortcut("nop_go")
        @app.command("/go")
        async def go_command(ack, body, say):
            await self._pause_unpause(body, ack, say, pause=False)

    async def test_send_message(self, msg='Hello *Slack*!'):
        await self.slack_app.client.chat_postMessage(channel='C02L2AVS937', text=msg, mrkdwn=True)

    def start_in_background(self):
        ...  # no action needed here

    @staticmethod
    def convert_html_to_my_format(text: str):
        text = text.replace('\n', '<br>')
        return HTMLSlacker(text).get_output()
