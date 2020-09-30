import json
from dataclasses import dataclass, asdict


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


@dataclass
class StakeTx(BaseModelMixin):
    type: str
    pool: str
    asset_amount: float
    rune_amount: float

    @classmethod
    def load_from_midgard(cls, j):
        t = j['type']
        pool = j['pool']

        if t == 'stake':
            coins = j['in']['coins']
            if coins[0]['asset'] == pool:
                asset_amount = coins[0]
                rune_amount = coins[1]
            else:
                asset_amount = coins[1]
                rune_amount = coins[0]
        elif t == 'unstake':
            out = j['out']
            if out[0]['coins'][0]['asset'] == pool:
                asset_amount = out[0]['coins'][0]
                rune_amount = out[1]['coins'][0]
            else:
                asset_amount = out[1]['coins'][0]
                rune_amount = out[0]['coins'][0]
        else:
            return None

        return cls(t, pool,
                   asset_amount=float(asset_amount['amount']) * MIDGARD_MULT,
                   rune_amount=float(rune_amount['amount']) * MIDGARD_MULT)
