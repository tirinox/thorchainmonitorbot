import json
from dataclasses import dataclass, asdict


MIDGARD_MULT = 10 ** -8

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

    @classmethod
    def error(cls):
        return cls(-1, -1, 1e-10)

    @property
    def cap_usd(self):
        return self.price * self.cap

    @property
    def is_ok(self):
        return self.cap >= 0
