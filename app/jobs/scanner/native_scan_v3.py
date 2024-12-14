from typing import Optional

from jobs.scanner.block_loader import BlockResult
from jobs.scanner.native_scan import BlockScanner


class BlockScannerV3(BlockScanner):
    async def fetch_one_block(self, block_index) -> Optional[BlockResult]:

        block = await self.deps.thor_connector.query_thorchain_block_raw(block_index)
        return block

