import asyncio

from web3 import Web3

from services.lib.config import Config
from services.lib.utils import WithLogger, async_wrap


class Web3Helper(WithLogger):
    def __init__(self, cfg: Config):
        super().__init__()
        key = cfg.as_str('infura.key', '-')
        self.cache_expire = cfg.as_interval('infura.cache_expire', '30d')
        self._retries = cfg.as_int('infura.retries', 3)
        self._retry_wait = cfg.as_interval('infura.retry_wait', '3s')
        self.w3 = Web3(Web3.HTTPProvider(f'https://mainnet.infura.io/v3/{key}'))

    async def _retry_action(self, coroutine):
        for _ in range(self._retries):
            try:
                return await coroutine
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
