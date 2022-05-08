import asyncio

import tweepy

from services.lib.config import Config
from services.lib.utils import class_logger, sep
from services.notify.channel import MessageType


class TwitterBot:
    LIMIT_CHARACTERS = 280

    def __init__(self, cfg: Config):
        self.cfg = cfg
        keys = cfg.get('twitter.bot')

        consumer_key = keys.as_str('consumer_key')
        consumer_secret = keys.as_str('consumer_secret')
        access_token = keys.as_str('access_token')
        access_token_secret = keys.as_str('access_token_secret')
        assert consumer_key and consumer_secret and access_token and access_token_secret

        self.auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
        self.auth.set_access_token(access_token, access_token_secret)
        self.api = tweepy.API(self.auth)
        self.logger = class_logger(self)

    def verify_credentials(self):
        try:
            self.api.verify_credentials()
            self.logger.debug('Good!')
            return True
        except Exception as e:
            self.logger.debug(f'Bad: {e!r}!')
            return False

    def post_sync(self, text: str):
        if not text:
            return
        if len(text) >= self.LIMIT_CHARACTERS:
            self.logger.warning(f'Too long text ({len(text)} symbols): "{text}".')
            text = text[:self.LIMIT_CHARACTERS]

        return self.api.update_status(text)

    async def post(self, text: str, executor=None, loop=None):
        if not text:
            return
        loop = loop or asyncio.get_event_loop()
        return await loop.run_in_executor(executor, self.post_sync, text)

    async def safe_send_message(self, chat_id, text, message_type=MessageType.TEXT, **kwargs) -> bool:
        if message_type == MessageType.TEXT:
            await self.post(text)  # Chat_id is not supported yet... only one single channel
        else:
            self.logger.error('Image uploading is not implemented. Yet.')  # todo: image uploading
            return False
        return True


class TwitterBotMock(TwitterBot):
    def post_sync(self, text: str):
        sep()
        self.logger.info(f'🐦🐦🐦 Tweets: "{text}". 🐦🐦🐦')
        sep()
