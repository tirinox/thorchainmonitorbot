from dataclasses import dataclass

from services.models.tx import ThorTxType


@dataclass
class THORMemoParsed:
    action: str
    asset: str
    dest_address: str = ''
    limit: int = 0
    affiliate_address: str = ''
    affiliate_fee: float = 0.0
    dex_aggregator_address: str = ''
    final_asset_address: str = ''
    min_amount_out: int = 0

    # 0    1     2        3   4         5   6                   7                8
    # SWAP:ASSET:DESTADDR:LIM:AFFILIATE:FEE:DEX Aggregator Addr:Final Asset Addr:MinAmountOut

    @staticmethod
    def ith_or_default(a, index, default=None):
        return a[index] if 0 <= index < len(a) else default

    @classmethod
    def parse_memo(cls, memo: str):
        components = [it.upper() for it in memo.split(':')]
        action = cls.ith_or_default(components, 0).lower()

        if action == ThorTxType.TYPE_SWAP:
            return cls(
                action,
                asset=cls.ith_or_default(components, 1),
                dest_address=cls.ith_or_default(components, 2),
                limit=int(cls.ith_or_default(components, 3)),
                affiliate_address=cls.ith_or_default(components, 4),
                affiliate_fee=float(cls.ith_or_default(components, 5) / 10_000.0),
                dex_aggregator_address=cls.ith_or_default(components, 6),
                final_asset_address=cls.ith_or_default(components, 7),
                min_amount_out=int(cls.ith_or_default(components, 8))
            )
