from typing import NamedTuple, Optional

from services.lib.texts import fuzzy_search
from services.lib.utils import load_json

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


class TokenList:
    DEFAULT_TOKEN_LIST_ETH_PATH = f'{CONTRACT_DATA_BASE_PATH}/eth_mainnet_V97.json'
    DEFAULT_TOKEN_LIST_AVAX_PATH = f'{CONTRACT_DATA_BASE_PATH}/avax_mainnet_V95.json'

    def __init__(self, filename, chain):
        self.chain = chain
        data = load_json(filename)
        tokens = [
            TokenRecord(
                t.get('address'),
                int(t.get('chainId', 0)),
                int(t.get('decimals', 18)),
                t.get('name'),
                t.get('symbol'),
                t.get('logoURI')
            ) for t in data['tokens']
        ]
        self.tokens = {
            t.address.lower(): t for t in tokens
        }

    def __len__(self):
        return len(self.tokens)

    def __getitem__(self, item) -> Optional[TokenRecord]:
        return self.tokens[str(item).lower()]

    def fuzzy_search(self, query):
        variants = fuzzy_search(query, self.tokens.keys(), f=str.lower)
        return [self.tokens.get(v) for v in variants]
