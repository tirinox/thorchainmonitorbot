import ujson
from dataclasses import dataclass, asdict


@dataclass
class BaseModelMixin:
    @property
    def as_json_string(self):
        return ujson.dumps(asdict(self))

    @classmethod
    def from_json(cls, jstr):
        if not jstr:
            return None
        d = ujson.loads(jstr)
        return cls(**d)
