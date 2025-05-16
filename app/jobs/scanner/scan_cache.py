import ujson

from jobs.scanner.native_scan import BlockScanner
from lib.depcont import DepContainer


class BlockScannerCached(BlockScanner):
    DB_KEY_BLOCK = 'tx:__cache:block'

    def __init__(self, deps: DepContainer,
                 sleep_period=None, last_block=0,
                 max_attempts=BlockScanner.MAX_ATTEMPTS_TO_SKIP_BLOCK):
        super().__init__(deps, sleep_period, last_block, max_attempts)

    async def _fetch_raw_block(self, block_no):
        cached_data = await self.deps.db.redis.hget(self.DB_KEY_BLOCK, str(block_no))
        if cached_data:
            return ujson.loads(cached_data)
        else:
            real_block = await super()._fetch_raw_block(block_no)
            if real_block:
                await self.deps.db.redis.hset(self.DB_KEY_BLOCK, str(block_no), ujson.dumps(real_block))
            return real_block
