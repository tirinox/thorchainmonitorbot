import asyncio

from web3 import Web3
from web3.exceptions import TransactionNotFound
from web3.types import TxData, TxReceipt

from lib.cache import Cache
from lib.config import Config
from lib.db import DB
from lib.utils import WithLogger, async_wrap


class Web3Helper(WithLogger):
    @property
    def logger_prefix(self):
        return f'[{self.chain}] '

    def __init__(self, cfg: Config, chain: str):
        self.chain = chain
        super().__init__()

        self.cache_expire = cfg.as_interval('web3.cache_expire', '30d')
        self._retries = cfg.as_int('web3.retries', 3)
        self._retry_wait = cfg.as_interval('web3.retry_wait', '3s')

        rpc_url = cfg.as_str(f'web3.{chain}.rpc')
        self.logger.info(f'Init Web3 for {chain} @ "{rpc_url}".')
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))

    async def _retry_action(self, coroutine):
        for _ in range(self._retries):
            try:
                return await coroutine
            except TransactionNotFound:
                raise
            except Exception:
                self.logger.exception(f'failed to load WEB3 data for {coroutine}', exc_info=True)
                if self._retry_wait > 0:
                    await asyncio.sleep(self._retry_wait)

    @async_wrap
    def _get_transaction(self, tx_id):
        return self.w3.eth.get_transaction(tx_id)

    async def get_transaction(self, tx_id):
        return await self._retry_action(self._get_transaction(tx_id))

    @async_wrap
    def _get_transaction_receipt(self, tx_id):
        return self.w3.eth.get_transaction_receipt(tx_id)

    async def get_transaction_receipt(self, tx_id):
        return await self._retry_action(self._get_transaction_receipt(tx_id))


class Web3HelperCached(Web3Helper):
    def __init__(self, chain, cfg: Config, db: DB):
        super().__init__(cfg, chain)
        self.db = db
        self._tx_cache = Cache(db, f'W3:Cache:{chain}:TX')
        self._tx_receipt_cache = Cache(db, f'W3:Cache:{chain}:TXReceipt')

    async def get_transaction(self, tx_id):
        if previous := await self._tx_cache.load(tx_id):
            return TxData(previous)
        tx = await super().get_transaction(tx_id)
        if tx:
            await self._tx_cache.store(tx_id, tx)
        return tx

    async def get_transaction_receipt(self, tx_id):
        if previous := await self._tx_receipt_cache.load(tx_id):
            return TxReceipt(previous)
        tx = await super().get_transaction_receipt(tx_id)
        if tx:
            await self._tx_receipt_cache.store(tx_id, tx)
        return tx
