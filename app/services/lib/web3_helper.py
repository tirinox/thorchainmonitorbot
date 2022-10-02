from typing import NamedTuple

from web3 import Web3

from services.lib.config import Config
from services.lib.utils import WithLogger, load_json


class Web3Helper(WithLogger):
    def __init__(self, cfg: Config):
        super().__init__()
        key = cfg.as_str('infura.key')
        self.w3 = Web3(Web3.AsyncHTTPProvider(f'https://mainnet.infura.io/v3/{key}'))


class TokenRecord(NamedTuple):
    address: str
    chain_id: int
    decimals: int
    name: str
    symbol: str
    logoURI: str


class TokenList:
    DEFAULT_TOKEN_LIST_ETH_PATH = '../../data/token_list/eth_mainnet_V97.json'
    DEFAULT_TOKEN_LIST_AVAX_PATH = '../../data/token_list/avax_mainnet_V95.json'

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

    def __getitem__(self, item):
        return self.tokens[str(item).lower()]
