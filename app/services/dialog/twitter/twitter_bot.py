import asyncio
import logging
from contextlib import suppress
from typing import Optional

import tweepy
from ratelimit import limits

from services.dialog.twitter.text_length import twitter_text_length, twitter_cut_text, TWITTER_LIMIT_CHARACTERS
from services.lib.config import Config
from services.lib.date_utils import DAY
from services.lib.draw_utils import img_to_bio
from services.lib.emergency import EmergencyReport
from services.lib.utils import class_logger, random_hex
from services.notify.channel import MessageType, BoardMessage, MESSAGE_SEPARATOR


class TwitterBot:
    MAX_TWEETS_PER_DAY = 300

    def __init__(self, cfg: Config):
        self.cfg = cfg
        keys = cfg.get('twitter.bot')

        consumer_key = keys.as_str('consumer_key')
        consumer_secret = keys.as_str('consumer_secret')
        access_token = keys.as_str('access_token')
        access_token_secret = keys.as_str('access_token_secret')
        assert consumer_key and consumer_secret and access_token and access_token_secret

        # self.auth = tweepy.OAuth2BearerHandler(bearer_token)
        self.auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
        self.auth.set_access_token(access_token, access_token_secret)
        self.api = tweepy.API(self.auth)
        self.client = tweepy.Client(consumer_key=consumer_key, consumer_secret=consumer_secret,
                                    access_token=access_token, access_token_secret=access_token_secret)
        self.logger = class_logger(self)

        self.emergency: Optional[EmergencyReport] = None

    async def verify_credentials(self, loop=None):
        try:
            loop = loop or asyncio.get_event_loop()
            await loop.run_in_executor(None, self.api.verify_credentials)
            self.logger.debug('Good!')
            return True
        except Exception as e:
            self.logger.error(f'Bad: {e!r}!')
            return False

    def log_tweet(self, text, image):
        img_tag = "with image" if bool(image) else ""
        self.logger.info(f'🐦🐦🐦 Tweets [{twitter_text_length(text)} symbols]: "\n{text}\n". 🐦🐦🐦 {img_tag}')

    @limits(calls=MAX_TWEETS_PER_DAY, period=DAY)
    def post_sync(self, text: str, image=None):
        if not text:
            return

        real_len = twitter_text_length(text)
        if real_len >= TWITTER_LIMIT_CHARACTERS:
            self.logger.warning(f'Too long text ({real_len} symbols): "{text}".')
            text = twitter_cut_text(text, TWITTER_LIMIT_CHARACTERS)

        self.log_tweet(text, image)

        if image:
            name = f'image-{random_hex()}.png'
            image_bio = img_to_bio(image, name)
            ret = self.api.media_upload(filename=name, file=image_bio)

            # Attach media to tweet
            # return self.api.update_status(media_ids=[ret.media_id_string], status=text)

            return self.client.create_tweet(text=text, media_ids=[ret.media_id_string])
        else:
            return self.client.create_tweet(text=text)
            # return self.api.update_status(text)

    async def post(self, text: str, image=None, executor=None, loop=None):
        if not text:
            return
        loop = loop or asyncio.get_event_loop()
        await loop.run_in_executor(executor, self.post_sync, text, image)

    async def multi_part_post(self, text: str, image=None, executor=None, loop=None):
        parts = text.split(MESSAGE_SEPARATOR, maxsplit=10)
        parts = list(filter(bool, map(str.strip, parts)))

        if not parts:
            logging.warning('Oops? The message has zero parts. Did nothing.')
            return
        elif len(parts) >= 2:
            logging.info(f'Sending Twitter multi-part message: {len(parts) = }')

        loop = loop or asyncio.get_event_loop()

        for part in reversed(parts):  # post in reversed order to make it look logical
            await self.post(part, image, executor, loop)
            image = None  # attach image solely to the first post, then just nullify it

    async def send_message(self, chat_id, msg: BoardMessage, _retrying=False, **kwargs) -> bool:
        # Chat_id is not supported yet... only one single channel
        try:
            if msg.message_type == MessageType.TEXT:
                await self.multi_part_post(msg.text)
            elif msg.message_type == MessageType.PHOTO:
                await self.multi_part_post(msg.text, image=msg.photo)
            else:
                logging.warning(f'Type "{msg.message_type}" is not supported for Twitter.')
            return True
        except tweepy.errors.Forbidden as e:
            if self.emergency:
                with suppress(Exception):
                    # Signal the admin to update app binding in the Twitter Developer Portal
                    self.emergency.report(self.logger.name, "Twitter forbidden error",
                                          api_errors=e.api_errors,
                                          api_codes=e.api_codes,
                                          api_messages=e.api_messages)
            if _retrying:
                logging.exception('Tried to resend Twitter message. Failed again.')
                return False
            else:
                # logging.warning(f'There is an exception: {e!r}. But I will try to abbreviate the message and resend.')
                # msg.text = abbreviate_some_long_words(msg.text)
                # self.log_tweet(msg.text, None)

                logging.warning(f'There is an exception: {e!r}. But I will try to resend the message as is.')
                await asyncio.sleep(15)
                return await self.send_message(chat_id, msg, _retrying=True, **kwargs)
        except Exception:
            logging.exception(f'Twitter exception!', stack_info=True)
            return False


class TwitterBotMock(TwitterBot):
    def __init__(self, cfg: Config):
        super().__init__(cfg)
        self.exceptions = bool(cfg.get('twitter.mock_raise', False))

    def post_sync(self, text: str, image=None):
        self.log_tweet(text, image)
        if self.exceptions:
            raise Exception('Alas! Mock exception!')
