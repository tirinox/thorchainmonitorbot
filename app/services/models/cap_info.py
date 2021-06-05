from dataclasses import dataclass

from services.models.base import BaseModelMixin


@dataclass
class ThorCapInfo(BaseModelMixin):
    cap: int
    pooled_rune: int
    price: float

    MAX_ALLOWED_RATIO = 0.9

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

    @property
    def can_add_liquidity(self):
        return self.cap > 0 and self.pooled_rune / self.cap < self.MAX_ALLOWED_RATIO

    @property
    def how_much_rune_you_can_lp(self):
        return max(0.0, self.cap * self.MAX_ALLOWED_RATIO - self.pooled_rune)
