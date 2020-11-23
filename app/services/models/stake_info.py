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
