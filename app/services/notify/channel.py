import typing


class Messengers:
    TELEGRAM = 'telegram'
    SLACK = 'slack'
    DISCORD = 'discord'

    SUPPORTED = [
        TELEGRAM,
        SLACK,
        DISCORD
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
