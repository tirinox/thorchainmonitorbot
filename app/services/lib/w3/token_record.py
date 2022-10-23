import json
from typing import NamedTuple, Optional


class TokenRecord(NamedTuple):
    address: str
    chain_id: int
    decimals: int
    name: str
    symbol: str
    logoURI: str


CONTRACT_DATA_BASE_PATH = './data/token_list'


class AmountToken(NamedTuple):
    amount: float
    token: TokenRecord
    aggr_name: str = ''

    @property
    def as_json(self):
        return {
            'amount': self.amount,
            'aggr_name': self.aggr_name,
            'symbol': self.token.symbol
        }

    @classmethod
    def from_json(cls, j: str):
        try:
            j = json.loads(j)
        except json.JSONDecodeError:
            j = None
        if not j:
            return

        amount = float(j.get('amount', 0.0))
        if not amount:
            return

        token_symbol = j.get('symbol', '')
        return cls(
            amount=amount,
            aggr_name=j.get('aggr_name', ''),
            token=TokenRecord(
                '', 0, 18, token_symbol, token_symbol, ''
            )
        )


class SwapInOut(NamedTuple):
    swap_in: Optional[AmountToken] = None
    swap_out: Optional[AmountToken] = None
