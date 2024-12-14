import ujson

from jobs.scanner.native_scan import BlockScanner
from lib.depcont import DepContainer


class BlockScannerCached(BlockScanner):
    DB_KEY_BLOCK = 'tx:scanner:cache:block'
    DB_KEY_TXS = 'tx:scanner:cache:transactions'

    def __init__(self, deps: DepContainer,
                 sleep_period=None, last_block=0,
                 max_attempts=BlockScanner.MAX_ATTEMPTS_TO_SKIP_BLOCK):
        super().__init__(deps, sleep_period, last_block, max_attempts)

    async def _fetch_block_results_raw(self, block_no):
        cached_data = await self.deps.db.redis.hget(self.DB_KEY_BLOCK, str(block_no))
        if cached_data:
            return ujson.loads(cached_data)
        else:
            real_block = await super()._fetch_block_results_raw(block_no)
            if real_block:
                await self.deps.db.redis.hset(self.DB_KEY_BLOCK, str(block_no), ujson.dumps(real_block))
            return real_block

    async def _fetch_block_txs_raw(self, block_no):
        cached_data = await self.deps.db.redis.hget(self.DB_KEY_TXS, str(block_no))
        if cached_data:
            return ujson.loads(cached_data)
        else:
            real_block_txs = await super()._fetch_block_txs_raw(block_no)
            if real_block_txs:
                await self.deps.db.redis.hset(self.DB_KEY_TXS, str(block_no), ujson.dumps(real_block_txs))
            return real_block_txs
