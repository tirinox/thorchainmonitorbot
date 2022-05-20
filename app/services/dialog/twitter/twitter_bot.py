import asyncio

import tweepy

from services.lib.config import Config
from services.lib.utils import class_logger, random_hex
from services.notify.channel import MessageType, BoardMessage


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

    def post_sync(self, text: str, image=None):
        if not text:
            return
        if len(text) >= self.LIMIT_CHARACTERS:
            self.logger.warning(f'Too long text ({len(text)} symbols): "{text}".')
            text = text[:self.LIMIT_CHARACTERS]

        if image:
            name = f'image-{random_hex()}.png'
            ret = self.api.media_upload(filename=name, file=image)

            # Attach media to tweet
            return self.api.update_status(media_ids=[ret.media_id_string], status=text)
        else:
            return self.api.update_status(text)

    async def post(self, text: str, image=None, executor=None, loop=None):
        if not text:
            return
        loop = loop or asyncio.get_event_loop()
        return await loop.run_in_executor(executor, self.post_sync, text, image)

    async def safe_send_message(self, chat_id, msg: BoardMessage, **kwargs) -> bool:
        if msg.message_type == MessageType.TEXT:
            await self.post(msg.text)  # Chat_id is not supported yet... only one single channel
        elif msg.message_type == MessageType.PHOTO:
            await self.post(msg.text, image=msg.photo)
        return True


class TwitterBotMock(TwitterBot):
    def post_sync(self, text: str, image=None):
        self.logger.info(f'🐦🐦🐦 Tweets: "{text}". 🐦🐦🐦 Img = {bool(image)}')
