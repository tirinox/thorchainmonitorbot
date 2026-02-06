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
    msg_type: str = ""

    @classmethod
    def make_photo(cls, photo, caption='', photo_file_name='photo.png', msg_type=None):
        return cls(caption, MessageType.PHOTO, photo, photo_file_name, msg_type or 'unknown_photo')

    @property
    def is_empty(self):
        return not self.text and not self.photo

    def get_bio(self):
        return img_to_bio(self.photo, self.photo_file_name)

    def __repr__(self):
        extra_tag = ''
        if self.photo:
            if hasattr(self.photo, 'width'):
                photo_size = f"{self.photo.width}x{self.photo.height}"
            elif isinstance(self.photo, bytes):
                photo_size = f"{len(self.photo)} bytes"
            else:
                photo_size = f"unknown size"
            extra_tag += f', with {self.photo_file_name!r} ({photo_size})'
        return f'BoardMessage({self.text!r}{extra_tag})'


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
