import asyncio
import logging

from services.jobs.fetch.native_scan import NativeScannerTX, NativeScannerBlockEvents
from services.jobs.transfer_detector import RuneTransferDetector
from services.lib.config import Config
from services.lib.delegates import INotified
from services.lib.utils import setup_logs, sep


class Receiver(INotified):
    # noinspection PyTypeChecker
    async def on_data(self, sender, data):
        sep()
        for tr in data:
            print(tr)


async def t_tx_scanner(url):
    scanner = NativeScannerTX(url)
    detector = RuneTransferDetector()
    scanner.subscribe(detector)
    detector.subscribe(Receiver())
    await scanner.run()


async def t_block_scanner(url):
    scanner = NativeScannerBlockEvents(url)
    scanner.subscribe(Receiver())
    await scanner.run()


async def main():
    cfg = Config()
    url = cfg.as_str('thor.node.rpc_node_url')
    await t_block_scanner(url)


if __name__ == '__main__':
    setup_logs(logging.INFO)
    asyncio.run(main())
