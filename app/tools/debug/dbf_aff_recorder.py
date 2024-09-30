import asyncio
import logging

from jobs.scanner.affliliate_recorder import AffiliateRecorder
from jobs.scanner.native_scan import NativeScannerBlock
from tools.lib.lp_common import LpAppFramework


async def dbg_aff_record1(app, send_alerts=False, catch_up=0, force_start_block=None, one_block=False):
    d = app.deps
    d.block_scanner = NativeScannerBlock(d)

    await d.pool_fetcher.run_once()

    d.last_block_fetcher.add_subscriber(d.last_block_store)

    # AffiliateRecorder
    d.affiliate_recorder = AffiliateRecorder(d)
    d.block_scanner.add_subscriber(d.affiliate_recorder)

    await d.last_block_fetcher.run_once()

    # if print_txs:
    #     detector.add_subscriber(Receiver('Transfer'))

    if catch_up > 0:
        await d.block_scanner.ensure_last_block()
        d.block_scanner.last_block -= catch_up
    elif force_start_block:
        d.block_scanner.last_block = force_start_block

    if one_block:
        d.block_scanner.one_block_per_run = True
        await d.block_scanner.run_once()
    else:
        await d.block_scanner.run()


async def main():
    app = LpAppFramework(log_level=logging.INFO)
    async with app(brief=True):
        # await dbg_aff_record1(app, catch_up=50)
        await dbg_aff_record1(app, one_block=True, force_start_block=16089600)


if __name__ == '__main__':
    asyncio.run(main())
