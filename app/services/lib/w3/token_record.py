from typing import NamedTuple

ETH_CHAIN_ID = 0x1
AVAX_CHAIN_ID = 43114


class TokenRecord(NamedTuple):
    address: str
    chain_id: int
    decimals: int
    name: str
    symbol: str
    logoURI: str


CONTRACT_DATA_BASE_PATH = './data/token_list'
