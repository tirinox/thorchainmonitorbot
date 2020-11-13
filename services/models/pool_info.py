from dataclasses import dataclass

MIDGARD_MULT = 10 ** -8


@dataclass
class PoolInfo:
    asset: str
    price: float  # runes per 1 asset

    balance_asset: int
    balance_rune: int

    enabled: bool

    @classmethod
    def dummy(cls):
        return cls('', 1, 1, 1, False)

    def usd_depth(self, dollar_per_rune):
        pool_depth_usd = self.balance_rune * MIDGARD_MULT * dollar_per_rune
        return pool_depth_usd

    @classmethod
    def from_dict(cls, j):
        balance_asset = int(j['balance_asset'])
        balance_rune = int(j['balance_rune'])
        return cls(asset=j['asset'],
                   price=(balance_asset / balance_rune),
                   balance_asset=balance_asset,
                   balance_rune=balance_rune,
                   enabled=(j['status'] == 'Enabled'))

    @property
    def to_dict(self):
        return {
            'balance_asset': self.balance_asset,
            'balance_rune': self.balance_rune
        }
