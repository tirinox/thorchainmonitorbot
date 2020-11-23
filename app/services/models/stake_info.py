from dataclasses import dataclass, field

from services.models.base import BaseModelMixin

BNB_CHAIN = 'BNB'
BECH_2_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


@dataclass
class MyStakeAddress(BaseModelMixin):
    address: str = ''
    chain: str = BNB_CHAIN
    pools: list = field(default_factory=list)

    @classmethod
    def is_good_address(cls, addr: str, chain=BNB_CHAIN):
        if chain == BNB_CHAIN:
            addr = addr.strip()

            return (addr.startswith('bnb1')
                    and 30 <= len(addr) <= 50
                    and set(addr[4:]) < set(BECH_2_CHARSET))
        else:
            return False


@dataclass
class CurrentLiquidity(BaseModelMixin):
    pool: str
    rune_stake: int
    asset_stake: int
    pool_units: int
    asset_withdrawn: int
    rune_withdrawn: int
    total_staked_asset: int
    total_staked_rune: int
    total_staked_usd: float
    total_unstaked_asset: float
    total_unstaked_rune: float
    total_unstaked_usd: float
    first_stake: int
    last_stake: int

    @classmethod
    def from_asgard(cls, d):
        return cls(
            d['pool'], d['runestake'], d['assetstake'], d['poolunits'],
            d['assetwithdrawn'], d['runewithdrawn'],
            d['totalstakedasset'], d['totalstakedrune'],
            d['totalstakedusd'], d['totalunstakedasset'],
            d['totalunstakedrune'], d['totalunstakedusd'],
            d['firststake'], d['laststake']
        )