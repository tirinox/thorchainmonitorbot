import typing
from dataclasses import dataclass
from enum import Enum

CHANNEL_INACTIVE = 'channel_inactive'


class MessageType(Enum):
    TEXT = 'text'
    STICKER = 'sticker'
    PHOTO = 'photo'


@dataclass
class BoardMessage:
    text: str
    message_type: MessageType = MessageType.TEXT
    photo: str = None

    @classmethod
    def make_photo(cls, photo, caption=''):
        return cls(caption, MessageType.PHOTO, photo)


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
    lang: str = 'eng'

    @classmethod
    def from_json(cls, j):
        channel_type = str(j.get('type')).strip().lower()
        assert channel_type in Messengers.SUPPORTED

        return cls(
            channel_type,
            j.get('name', ''),
            j.get('lang', 'eng'),
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
