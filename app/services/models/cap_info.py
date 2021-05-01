from dataclasses import dataclass

from services.models.base import BaseModelMixin


@dataclass
class ThorCapInfo(BaseModelMixin):
    cap: int
    pooled_rune: int
    price: float

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
        return self.cap >= 1 and self.pooled_rune >= 1
