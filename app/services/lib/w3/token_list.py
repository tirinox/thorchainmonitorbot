from typing import Optional

import web3

from services.lib.cache import CacheNamedTuple
from services.lib.db import DB
from services.lib.texts import fuzzy_search
from services.lib.utils import load_json
from services.lib.w3.erc20_contract import ERC20Contract
from services.lib.w3.token_record import TokenRecord, CONTRACT_DATA_BASE_PATH
from services.lib.w3.web3_helper import Web3Helper


class StaticTokenList:
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


class TokenListCached:
    def __init__(self, db: DB, w3: Web3Helper, static_list: StaticTokenList):
        self.static_list = static_list
        self.db = db
        self.w3 = w3
        self._cache = CacheNamedTuple(db, self.DB_KEY_TOKEN_CACHE, TokenRecord)

    DB_KEY_TOKEN_CACHE = 'Tokens:Cache'

    async def resolve_token(self, address: str) -> Optional[TokenRecord]:
        results = self.static_list.fuzzy_search(address)
        if len(results) >= 1:
            return results[0]

        if not web3.Web3.isAddress(address):
            return

        existing_data = await self._cache.load(address)
        if existing_data:
            return existing_data

        erc20 = ERC20Contract(self.w3, address, self.static_list.chain)
        info = await erc20.get_token_info()

        if info:
            await self._cache.store(address, info)

        return info

    async def clear_cache(self):
        await self._cache.clear()
