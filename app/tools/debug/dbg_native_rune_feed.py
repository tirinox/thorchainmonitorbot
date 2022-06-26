import asyncio
import logging

from services.jobs.fetch.native_scan import NativeScannerTX, NativeScannerBlockEvents
from services.jobs.transfer_detector import RuneTransferDetectorNativeTX, RuneTransferDetectorBlockEvents
from services.lib.config import Config
from services.lib.delegates import INotified
from services.lib.utils import setup_logs
from services.lib.texts import sep


class Receiver(INotified):
    # noinspection PyTypeChecker
    async def on_data(self, sender, data):
        sep()
        for tr in data:
            print(f'{self.tag}:  {tr}')

    def __init__(self, tag=''):
        self.tag = tag


async def t_tx_scanner(url):
    scanner = NativeScannerTX(url)
    detector = RuneTransferDetectorNativeTX()
    scanner.subscribe(detector)
    scanner.subscribe(Receiver('TX'))
    detector.subscribe(Receiver('Transfer'))
    await scanner.run()


async def t_block_scanner(url):
    scanner = NativeScannerBlockEvents(url)
    detector = RuneTransferDetectorBlockEvents()
    scanner.subscribe(detector)
    detector.subscribe(Receiver())
    await scanner.run()


async def main():
    cfg = Config()
    url = cfg.as_str('thor.node.rpc_node_url')
    await t_tx_scanner(url)


if __name__ == '__main__':
    setup_logs(logging.INFO)
    asyncio.run(main())
