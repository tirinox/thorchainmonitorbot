import json
from dataclasses import dataclass, asdict


@dataclass
class BaseModelMixin:
    @property
    def as_json(self):
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, jstr):
        d = json.loads(jstr)
        return cls(**d)
