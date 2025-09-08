import asyncio
import logging

from jobs.scanner.native_scan import BlockScanner
from jobs.scanner.scan_cache import BlockScannerCached
from jobs.scanner.transfer_detector import RuneTransferDetector
from notify.public.cex_flow import CEXFlowNotifier
from notify.public.transfer_notify import RuneMoveNotifier
from tools.lib.lp_common import LpAppFramework


async def main():
    app = LpAppFramework(log_level=logging.INFO)
    async with app:
        d = app.deps
        last_block = await d.last_block_cache.get_thor_block()
        last_block -= 10000
        d.block_scanner = BlockScannerCached(d, max_attempts=5, last_block=last_block)

        reserve_address = d.cfg.as_str('native_scanner.reserve_address')
        transfer_decoder = RuneTransferDetector(reserve_address)
        d.block_scanner.add_subscriber(transfer_decoder)

        if d.cfg.get('token_transfer.enabled', True):
            d.rune_move_notifier = RuneMoveNotifier(d)
            d.rune_move_notifier.min_usd_native = 10
            d.rune_move_notifier.add_subscriber(d.alert_presenter)
            transfer_decoder.add_subscriber(d.rune_move_notifier)

        if d.cfg.get('token_transfer.flow_summary.enabled', True):
            cex_flow_notifier = CEXFlowNotifier(d)
            # cex_flow_notifier.summary_cd.cooldown = 10
            cex_flow_notifier.add_subscriber(d.alert_presenter)
            transfer_decoder.add_subscriber(cex_flow_notifier)

        await d.block_scanner.run()


if __name__ == '__main__':
    asyncio.run(main())
