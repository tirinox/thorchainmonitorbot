import json
from dataclasses import dataclass, asdict


@dataclass
class BaseModelMixin:
    @property
    def as_json_string(self):
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, jstr):
        if not jstr:
            return None
        d = json.loads(jstr)
        return cls(**d)
