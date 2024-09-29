import typing
from dataclasses import dataclass
from enum import Enum

import PIL.Image

from comm.localization.languages import Language
from lib.draw_utils import img_to_bio

CHANNEL_INACTIVE = 'channel_inactive'

# this string tells some messengers e.g. Twitter to split a long post into sub posts
MESSAGE_SEPARATOR = '------'


class MessageType(Enum):
    TEXT = 'text'
    STICKER = 'sticker'
    PHOTO = 'photo'


@dataclass
class BoardMessage:
    text: str
    message_type: MessageType = MessageType.TEXT
    photo: PIL.Image.Image = None
    photo_file_name: str = 'photo.png'

    @classmethod
    def make_photo(cls, photo, caption='', photo_file_name='photo.png'):
        return cls(caption, MessageType.PHOTO, photo, photo_file_name)

    @property
    def empty(self):
        return not self.text and not self.photo

    def get_bio(self):
        return img_to_bio(self.photo, self.photo_file_name)


class Messengers:
    TELEGRAM = 'telegram'
    SLACK = 'slack'
    DISCORD = 'discord'
    TWITTER = 'twitter'

    SUPPORTED = [
        TELEGRAM,
        SLACK,
        DISCORD,
        TWITTER,
    ]


class ChannelDescriptor(typing.NamedTuple):
    type: str  # aka Messenger
    name: str
    lang: str = Language.ENGLISH

    @classmethod
    def from_json(cls, j):
        channel_type = str(j.get('type')).strip().lower()
        assert channel_type in Messengers.SUPPORTED

        return cls(
            channel_type,
            j.get('name', ''),
            j.get('lang', Language.ENGLISH),
        )

    @property
    def channel_id(self):
        return self.name

    @property
    def short_coded(self):
        return f'{self.type}-{self.name}'

    @classmethod
    def from_short_code(cls, s: str):
        platform, name = s.strip().split('-')
        return cls(platform, name)
