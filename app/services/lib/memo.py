from dataclasses import dataclass
from typing import Union

from services.lib.constants import Chains
from services.lib.texts import fuzzy_search
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

        if action == ThorTxType.TYPE_SWAP or action == '=':
            return cls(
                ThorTxType.TYPE_SWAP,
                asset=cls.ith_or_default(components, 1),
                dest_address=cls.ith_or_default(components, 2),
                limit=cls.ith_or_default(components, 3, 0, dtype=int),
                affiliate_address=cls.ith_or_default(components, 4),
                affiliate_fee=cls.ith_or_default(components, 5, 0, dtype=int) / 10_000.0,
                dex_aggregator_address=cls.ith_or_default(components, 6),
                final_asset_address=cls.ith_or_default(components, 7),
                min_amount_out=cls.ith_or_default(components, 8, 0, dtype=int)
            )


class AggregatorResolver:
    TABLE = {
        'TSAggregatorUniswapV2': (Chains.ETH, '0xd31f7e39afECEc4855fecc51b693F9A0Cec49fd2'),
        'TSAggregatorUniswapV3-500': (Chains.ETH, '0x7C38b8B2efF28511ECc14a621e263857Fb5771d3'),
        'TSAggregatorUniswapV3 3000': (Chains.ETH, '0x0747c681e5ADa7936Ad915CcfF6cD3bd71DBF121'),
        'TSAggregatorUniswapV3 10000': (Chains.ETH, '0xd1ea5F7cE9dA98D0bd7B1F4e3E05985E88b1EF10'),
        'TSAggregator2LegUniswapV2 USDC': (Chains.ETH, '0x94a852F0a21E473078846cf88382dd8d15bD1Dfb'),
        'TSAggregator SUSHIswap': (Chains.ETH, '0x3660dE6C56cFD31998397652941ECe42118375DA'),
        'RangoThorchainOutputAggUniV2': (Chains.ETH, '0x0F2CD5dF82959e00BE7AfeeF8245900FC4414199'),
        'RangoThorchainOutputAggUniV3': (Chains.ETH, '0x2a7813412b8da8d18Ce56FE763B9eb264D8e28a8'),
    }

    INV_TABLE_UPPER_ADDRESS = {
        address.upper(): (name, chain, address) for name, (chain, address) in TABLE.items()
    }

    @classmethod
    def search_aggregator_address(cls, query: str):
        variants = fuzzy_search(query, cls.INV_TABLE_UPPER_ADDRESS.keys())
        if not variants:
            return None

        address = variants[0]
        return cls.INV_TABLE_UPPER_ADDRESS.get(address)
