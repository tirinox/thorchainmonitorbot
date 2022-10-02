import asyncio
from typing import NamedTuple, Optional

from web3 import Web3
from web3.eth import AsyncEth

from services.lib.config import Config
from services.lib.texts import fuzzy_search
from services.lib.utils import WithLogger, load_json, async_wrap


class Web3Helper(WithLogger):
    def __init__(self, cfg: Config):
        super().__init__()
        key = cfg.as_str('infura.key', '-')
        self.cache_expire = cfg.as_interval('infura.cache_expire', '30d')
        self._retries = cfg.as_int('infura.retries', 3)
        self._retry_wait = cfg.as_interval('infura.retry_wait', '3s')
        self.w3 = Web3(Web3.HTTPProvider(f'https://mainnet.infura.io/v3/{key}'))

    @async_wrap
    def _get_transaction(self, tx_id):
        return self.w3.eth.get_transaction(tx_id)

    async def get_transaction(self, tx_id):
        for _ in range(self._retries):
            try:
                return await self._get_transaction(tx_id)
            except Exception:
                self.logger.exception('failed to get tx', exc_info=True)
                if self._retry_wait > 0:
                    await asyncio.sleep(self._retry_wait)

    """
    Tasks:
        1. TX to aggregator => decode asset, amount
        2. get token name by token address
    """


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

    def __getitem__(self, item) -> Optional[TokenRecord]:
        return self.tokens[str(item).lower()]

    def fuzzy_search(self, query):
        variants = fuzzy_search(query, self.tokens.keys(), f=str.lower)
        return [self.tokens.get(v) for v in variants]
