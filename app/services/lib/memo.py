from dataclasses import dataclass
from typing import Union

from services.lib.constants import THOR_BASIS_POINT_MAX


@dataclass
class THORMemo:
    action: str
    asset: str
    dest_address: str = ''
    limit: int = 0
    affiliate_address: str = ''
    affiliate_fee: float = 0.0  # (0..1) range
    dex_aggregator_address: str = ''
    final_asset_address: str = ''
    min_amount_out: int = 0
    s_swap_interval: int = 0
    s_swap_quantity: int = 0

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

    @property
    def has_affiliate_part(self):
        return self.affiliate_address and self.affiliate_fee > 0

    @property
    def is_streaming(self):
        return self.s_swap_quantity > 1

    @classmethod
    def parse_memo(cls, memo: str):
        components = [it for it in memo.split(':')]
        action = cls.ith_or_default(components, 0, '').lower()

        limit_and_s_swap = cls.ith_or_default(components, 3, '')
        s_swap_components = limit_and_s_swap.split('/')

        limit = cls.ith_or_default(s_swap_components, 0, 0, int)
        s_swap_interval = cls.ith_or_default(s_swap_components, 1, 0, int)
        s_swap_quantity = cls.ith_or_default(s_swap_components, 2, 0, int)

        if action == 'swap' or action == '=' or action == 's':
            return cls(
                'swap',
                asset=cls.ith_or_default(components, 1),
                dest_address=cls.ith_or_default(components, 2),
                limit=limit,
                affiliate_address=cls.ith_or_default(components, 4),
                affiliate_fee=cls.ith_or_default(components, 5, 0, dtype=int) / THOR_BASIS_POINT_MAX,
                dex_aggregator_address=cls.ith_or_default(components, 6),
                final_asset_address=cls.ith_or_default(components, 7),
                min_amount_out=cls.ith_or_default(components, 8, 0, dtype=int),
                s_swap_interval=s_swap_interval,
                s_swap_quantity=s_swap_quantity
            )
