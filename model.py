import json
from dataclasses import dataclass, asdict


@dataclass
class ThorInfo:
    cap: int
    stacked: int
    price: float

    @property
    def as_json(self):
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, jstr):
        return cls(**json.loads(jstr, encoding='utf-8'))

    @classmethod
    def zero(cls):
        return cls(0, 0, 0)

    @property
    def cap_usd(self):
        return self.price * self.cap
