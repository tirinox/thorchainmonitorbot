from dataclasses import dataclass
from typing import Union

from services.lib.constants import THOR_BASIS_POINT_MAX
from services.models.tx_type import TxType

MEMO_ACTION_TABLE = {
    "add": TxType.ADD_LIQUIDITY,
    "+": TxType.ADD_LIQUIDITY,
    "withdraw": TxType.WITHDRAW,
    "wd": TxType.WITHDRAW,
    "-": TxType.WITHDRAW,
    "swap": TxType.SWAP,
    "s": TxType.SWAP,
    "=": TxType.SWAP,
    "limito": TxType.LIMIT_ORDER,
    "lo": TxType.LIMIT_ORDER,
    "out": TxType.OUTBOUND,
    "donate": TxType.DONATE,
    "d": TxType.DONATE,
    "bond": TxType.BOND,
    "unbond": TxType.UNBOND,
    "leave": TxType.LEAVE,
    # "yggdrasil+": TxYggdrasilFund,
    # "yggdrasil-": TxYggdrasilReturn,
    # "reserve": TxReserve,
    "refund": TxType.REFUND,
    # "migrate": TxMigrate,
    # "ragnarok": TxRagnarok,
    # "switch": TxType.SWITCH,
    # "noop": TxNoOp,
    # "consolidate": TxConsolidate,
    "name": TxType.THORNAME,
    "n": TxType.THORNAME,
    "~": TxType.THORNAME,
    "$+": TxType.LOAN_OPEN,
    "loan+": TxType.LOAN_OPEN,
    "$-": TxType.LOAN_CLOSE,
    "loan-": TxType.LOAN_CLOSE,
}


@dataclass
class THORMemo:
    action: str
    asset: str
    dest_address: str = ''
    limit: int = 0
    s_swap_interval: int = 0
    s_swap_quantity: int = 0
    affiliate_address: str = ''
    affiliate_fee: float = 0.0  # (0..1) range
    dex_aggregator_address: str = ''
    final_asset_address: str = ''
    min_amount_out: int = 0

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

    @property
    def uses_aggregator_out(self):
        return bool(self.dex_aggregator_address)

    @classmethod
    def parse_streaming_params(cls, ss: str):
        s_swap_components = ss.split('/')

        limit = cls.ith_or_default(s_swap_components, 0, 0, int)
        s_swap_interval = cls.ith_or_default(s_swap_components, 1, 0, int)
        s_swap_quantity = cls.ith_or_default(s_swap_components, 2, 1, int)
        return limit, s_swap_interval, s_swap_quantity

    @classmethod
    def parse_memo(cls, memo: str):
        gist, *_comment = memo.split('|', maxsplit=2)  # ignore comments

        components = [it for it in gist.split(':')]

        action = cls.ith_or_default(components, 0, '').lower()
        tx_type = MEMO_ACTION_TABLE.get(action)

        if tx_type == TxType.SWAP:
            # 0    1     2        3   4         5   6                   7                8
            # SWAP:ASSET:DESTADDR:LIM:AFFILIATE:FEE:DEX Aggregator Addr:Final Asset Addr:MinAmountOut
            asset = cls.ith_or_default(components, 1)
            dest_address = cls.ith_or_default(components, 2)
            limit_and_s_swap = cls.ith_or_default(components, 3, '')
            limit, s_swap_interval, s_swap_quantity = cls.parse_streaming_params(limit_and_s_swap)

            return cls(
                tx_type, asset, dest_address, limit, s_swap_interval, s_swap_quantity,
                affiliate_address=cls.ith_or_default(components, 4),
                affiliate_fee=cls.ith_or_default(components, 5, 0, dtype=int) / THOR_BASIS_POINT_MAX,
                dex_aggregator_address=cls.ith_or_default(components, 6),
                final_asset_address=cls.ith_or_default(components, 7),
                min_amount_out=cls.ith_or_default(components, 8, 0, dtype=int),
            )
        elif tx_type == TxType.LOAN_OPEN:
            # LOAN+:BTC.BTC:bc1YYYYYY:minBTC:affAddr:affPts:dexAgg:dexTarAddr:DexTargetLimit
            # 0     1       2         3      4       5      6      7          8
            limit_and_s_swap = cls.ith_or_default(components, 3, '')
            limit, s_swap_interval, s_swap_quantity = cls.parse_streaming_params(limit_and_s_swap)
            asset = cls.ith_or_default(components, 1)
            dest_address = cls.ith_or_default(components, 2)

            return cls(
                TxType.LOAN_OPEN,
                asset,
                dest_address,
                limit,
                s_swap_interval,
                s_swap_quantity,
                affiliate_address=cls.ith_or_default(components, 4),
                affiliate_fee=cls.ith_or_default(components, 5, 0, dtype=int) / THOR_BASIS_POINT_MAX,
                dex_aggregator_address=cls.ith_or_default(components, 6),
                final_asset_address=cls.ith_or_default(components, 7),
                min_amount_out=cls.ith_or_default(components, 8, 0, dtype=int)
            )
        elif tx_type == TxType.LOAN_CLOSE:
            # "LOAN-:BTC.BTC:bc1YYYYYY:minOut"
            #  0     1       2         3

            limit_and_s_swap = cls.ith_or_default(components, 3, '')
            limit, s_swap_interval, s_swap_quantity = cls.parse_streaming_params(limit_and_s_swap)

            asset = cls.ith_or_default(components, 1)
            dest_address = cls.ith_or_default(components, 2)

            return cls(
                TxType.LOAN_CLOSE, asset, dest_address, limit, s_swap_interval, s_swap_quantity
            )
