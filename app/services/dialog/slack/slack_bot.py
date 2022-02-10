from io import BytesIO
from typing import Optional

from markdownify import markdownify
from slack_bolt.adapter.starlette.async_handler import AsyncSlackRequestHandler
from slack_bolt.async_app import AsyncApp
from slack_bolt.oauth.async_oauth_settings import AsyncOAuthSettings
from slack_sdk.oauth.installation_store import FileInstallationStore
from slack_sdk.oauth.state_store import FileOAuthStateStore
from slack_sdk.web.async_client import AsyncWebClient

from localization import LocalizationManager
from services.dialog.picture.price_picture import price_graph_from_db
from services.lib.config import Config
from services.lib.date_utils import DAY
from services.lib.db import DB
from services.lib.draw_utils import img_to_bio
from services.lib.nop_links import SettingsManager
from services.lib.utils import class_logger

# example: https://github.com/slackapi/bolt-python/blob/main/examples/starlette/async_oauth_app.py

SLACK_MESSENGER = 'Slack'


class SlackBot:
    INSTALLATION_DIR = "./data/slack_db/installations"
    STATE_DIR = "./data/slack_db/states"
    SCOPES = [
        "channels:read",
        "chat:write", "im:history", 'reactions:write',
        'files:write',
    ]

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

    async def send_message_to_channel(self, channel, text: Optional[str] = '', picture=None, pic_name='pic.png',
                                      need_convert=True):
        if need_convert:
            text = markdownify(text)

        if picture:
            if not isinstance(picture, BytesIO):
                picture = img_to_bio(picture, pic_name)

            response = await self.slack_app.client.files_upload(
                file=picture,
                initial_comment=text,
                channel=channel,
            )
        else:
            response = await self.slack_app.client.chat_postMessage(
                channel=channel,
                text=text,
                mrkdwn=True)

        self.logger.info(f'Slack response: {response.data}')

    def setup_commands(self):
        app = self.slack_app

        @app.command("/settings")
        async def settings_command(ack, body):
            channel_id = body.get('channel_id')
            async with self._settings_manager.get_context(channel_id) as settings:
                token = await self._settings_manager.generate_new_token(channel_id)

                settings[self._settings_manager.KEY_MESSENGER] = {
                    'platform': SLACK_MESSENGER,
                    'username': body.get('user_name', 'user'),
                    'name': body.get('channel_name', '-'),
                }
                url = self._settings_manager.get_link(token)

                user_id = body.get('user_id')
                # todo: localization!
                await ack(f"Settings for <@{user_id}> your link is {url}!")

        @app.command("/pause")
        async def pause_command(ack, body):
            user_id = body["user_id"]
            await ack(f"Pause <@{user_id}>!")
            print(body)
            # todo

        @app.command("/go")
        async def go_command(ack, body):
            user_id = body["user_id"]
            await ack(f"Go <@{user_id}>!")
            print(body)
            # todo

        # fixme: debug
        @app.message("knock")
        async def ask_who(message, say):
            print(message)
            await say("_Who's there?_")

        # fixme: debug
        @app.message("rune price")
        async def ask_who(message):
            print(message)
            channel = message['channel']

            period = 7 * DAY
            graph = await price_graph_from_db(self.db, LocalizationManager(self.cfg).default, period=period)

            await self.send_message_to_channel(channel, picture=graph, text='Rune Price')

        # @app.event("message")
        # async def handle_message_events(body, logger, client: AsyncWebClient):
        #     logger.info(body)
        #     user = body.get('event', {}).get('user')
        #     if user:
        #         info = await client.users_profile_get(user=user, include_labels=True)
        #         print('---- user: ----')
        #         print(info)
        #         print('---------------')

        # fixme: remove?
        @app.shortcut("open_settings")
        async def handle_shortcuts(ack, body, logger):
            await ack()
            logger.info(body)

    async def test_send_message(self, msg='Hello *Slack*!'):
        await self.slack_app.client.chat_postMessage(channel='C02L2AVS937', text=msg, mrkdwn=True)

    def start_in_background(self):
        ...
