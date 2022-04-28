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
    type: str
    name: str
    id: int = 0
    lang: str = 'eng'

    @classmethod
    def from_json(cls, j):
        channel_type = str(j.get('type')).strip().lower()
        assert channel_type in Messengers.SUPPORTED

        return cls(
            channel_type,
            j.get('name', ''),
            int(j.get('id', 0)),
            j.get('lang', 'eng'),
        )

    @property
    def channel_id(self):
        return self.id or self.name
