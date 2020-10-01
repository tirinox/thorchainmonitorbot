import json
from dataclasses import dataclass, asdict

from services.config import DB

MIDGARD_MULT = 10 ** -8


@dataclass
class BaseModelMixin:
    @property
    def as_json(self):
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, jstr):
        return cls(**json.loads(jstr, encoding='utf-8'))


@dataclass
class ThorInfo(BaseModelMixin):
    cap: int
    stacked: int
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
        return self.cap >= 0

    KEY_INFO = 'th_info'
    KEY_ATH = 'th_ath_rune_price'

    # -- ath --

    @classmethod
    async def get_ath(cls, db: DB):
        try:
            ath_str = await db.redis.get(cls.KEY_ATH)
            return float(ath_str)
        except (TypeError, ValueError, AttributeError):
            return 0.0

    @classmethod
    async def update_ath(cls, db: DB, price):
        ath = await cls.get_ath(db)
        if price > ath:
            await db.redis.set(cls.KEY_ATH, price)
            return True
        return False

    # -- caps --

    @classmethod
    async def get_old_cap(cls, db: DB):
        try:
            j = await db.redis.get(cls.KEY_INFO)
            return ThorInfo.from_json(j)
        except (TypeError, ValueError, AttributeError, json.decoder.JSONDecodeError):
            return ThorInfo.zero()

    async def save(self, db: DB):
        if db.redis:
            await db.redis.set(self.KEY_INFO, self.as_json)
