import asyncio
import logging

from jobs.scanner.native_scan import BlockScanner
from jobs.scanner.scan_cache import BlockScannerCached
from tools.debug.dbg_swap_scan import debug_full_pipeline
from tools.lib.lp_common import LpAppFramework

BlockScannerClass = BlockScannerCached
print(BlockScannerClass, ' <= look!')
BlockScannerClass = BlockScanner


async def run():
    app = LpAppFramework(log_level=logging.DEBUG)
    async with app:

        # change swap status before to "observed_in"
        # run scanner to see the outbound detection

        await debug_full_pipeline(
            app,
            # start=24541138 - 5,  # before start
            start=24548352 - 5,  # outbound
            tx_id='9C00705E343059E99E0DCE45992777D32A34EB0FCB00D83D50026D22EEAC4CD8',
            single_block=False,
            ignore_traders=True,
        )


if __name__ == '__main__':
    asyncio.run(run())
