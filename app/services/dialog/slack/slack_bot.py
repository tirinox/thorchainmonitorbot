from io import BytesIO
from typing import Optional

from markdownify import markdownify
from slack_bolt.adapter.starlette.async_handler import AsyncSlackRequestHandler
from slack_bolt.async_app import AsyncApp
from slack_bolt.oauth.async_oauth_settings import AsyncOAuthSettings
from slack_sdk.oauth.installation_store import FileInstallationStore
from slack_sdk.oauth.state_store import FileOAuthStateStore
from slack_sdk.web.async_client import AsyncWebClient

from services.lib.config import Config
from services.lib.draw_utils import img_to_bio
from services.lib.utils import class_logger


# example: https://github.com/slackapi/bolt-python/blob/main/examples/starlette/async_oauth_app.py


#
# @app.command("/hello-socket-mode")
# async def hello_command(ack, body):
#     user_id = body["user_id"]
#     ack(f"Hi <@{user_id}>!")
#
#
# @app.message("knock")
# async def ask_who(message, say):
#     print(message)
#     await say("_Who's there?_")
#
#
# @app.event("message")
# async def handle_message_events(body, logger, client: AsyncWebClient):
#     logger.info(body)
#     user = body.get('event', {}).get('user')
#     if user:
#         info = await client.users_profile_get(user=user, include_labels=True)
#         print('---- user: ----')
#         print(info)
#         print('---------------')
#
#
# @app.shortcut("open_settings")
# async def handle_shortcuts(ack, body, logger):
#     await ack()
#     logger.info(body)
#

# async def start():
# handler = AsyncSocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
# await handler.connect_async()
# await Event().wait()

class SlackBot:
    INSTALLATION_DIR = "./data/slack_db/installations"
    STATE_DIR = "./data/slack_db/states"
    SCOPES = [
        "channels:read",
        "chat:write", "im:history", 'reactions:write'
    ]

    def __init__(self, cfg: Config):
        self.logger = class_logger(self)
        # self.client = SocketModeClient(
        #     # This app-level token will be used only for establishing a connection
        #     app_token=cfg.as_str('slack.bot.app_token'),  # xapp-A111-222-xyz
        #     # You will be using this WebClient for performing Web API calls in listeners
        #     web_client=AsyncWebClient(token=cfg.as_str('slack.bot.bot_token'))  # xoxb-111-222-xyz
        # )
        # # noinspection PyTypeChecker
        # self.client.socket_mode_request_listeners.append(self._process)

        oauth_settings = AsyncOAuthSettings(
            client_id=cfg.as_str('slack.bot.client_id'),
            client_secret=cfg.as_str('slack.bot.client_secret'),
            scopes=self.SCOPES,
            installation_store=FileInstallationStore(base_dir=self.INSTALLATION_DIR),
            state_store=FileOAuthStateStore(expiration_seconds=600, base_dir=self.STATE_DIR),
        )

        self.slack_app = AsyncApp(
            signing_secret=cfg.as_str('slack.bot.singing_secret'),
            oauth_settings=oauth_settings,
        )
        self.slack_handler = AsyncSlackRequestHandler(self.slack_app)
        self.setup_commands()

    async def send_message_to_channel(self, channel, text: Optional[str], picture=None, pic_name='pic.png',
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
            response = await self.slack_app.client.chat_postMessage(channel=channel,
                                                                    text=text)

        self.logger.info(f'Slack: {response.data}')

    def setup_commands(self):
        app = self.slack_app

        @app.command("/hello-socket-mode")
        async def hello_command(ack, body):
            user_id = body["user_id"]
            ack(f"Hi <@{user_id}>!")

        @app.message("knock")
        async def ask_who(message, say):
            print(message)
            await say("_Who's there?_")

        @app.event("message")
        async def handle_message_events(body, logger, client: AsyncWebClient):
            logger.info(body)
            user = body.get('event', {}).get('user')
            if user:
                info = await client.users_profile_get(user=user, include_labels=True)
                print('---- user: ----')
                print(info)
                print('---------------')

        @app.shortcut("open_settings")
        async def handle_shortcuts(ack, body, logger):
            await ack()
            logger.info(body)

    def start_in_background(self):
        ...
