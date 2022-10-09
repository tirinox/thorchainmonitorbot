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


class SwapInOut(NamedTuple):
    swap_in: Optional[AmountToken] = None
    swap_out: Optional[AmountToken] = None
