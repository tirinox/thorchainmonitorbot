from dataclasses import dataclass
from typing import Union

from services.lib.constants import THOR_BASIS_POINT_MAX
from services.models.tx import ThorTxType


@dataclass
class THORMemoParsed:
    action: str
    asset: str
    dest_address: str = ''
    limit: int = 0
    affiliate_address: str = ''
    affiliate_fee: float = 0.0  # (0..1) range
    dex_aggregator_address: str = ''
    final_asset_address: str = ''
    min_amount_out: int = 0

    # 0    1     2        3   4         5   6                   7                8
    # SWAP:ASSET:DESTADDR:LIM:AFFILIATE:FEE:DEX Aggregator Addr:Final Asset Addr:MinAmountOut

    @staticmethod
    def ith_or_default(a, index, default=None, dtype: type = str) -> Union[str, int, float]:
        if 0 <= index < len(a):
            try:
                r = a[index].strip()
                if r == '':
                    return default
                return dtype(r)
            except ValueError:
                return default
        else:
            return default

    @classmethod
    def parse_memo(cls, memo: str):
        components = [it for it in memo.split(':')]
        action = cls.ith_or_default(components, 0).lower()

        if action == ThorTxType.TYPE_SWAP or action == '=' or action == 's':
            return cls(
                ThorTxType.TYPE_SWAP,
                asset=cls.ith_or_default(components, 1),
                dest_address=cls.ith_or_default(components, 2),
                limit=cls.ith_or_default(components, 3, 0, dtype=int),
                affiliate_address=cls.ith_or_default(components, 4),
                affiliate_fee=cls.ith_or_default(components, 5, 0, dtype=int) / THOR_BASIS_POINT_MAX,
                dex_aggregator_address=cls.ith_or_default(components, 6),
                final_asset_address=cls.ith_or_default(components, 7),
                min_amount_out=cls.ith_or_default(components, 8, 0, dtype=int)
            )
