import asyncio
import logging

from services.jobs.fetch.native_scan import NativeScannerTX, NativeScannerBlockEvents
from services.jobs.transfer_detector import RuneTransferDetectorNativeTX, RuneTransferDetectorBlockEvents, \
    RuneTransferDetectorFromTxResult
from services.lib.config import Config
from services.lib.delegates import INotified
from services.lib.texts import sep
from services.lib.utils import setup_logs


class Receiver(INotified):
    # noinspection PyTypeChecker
    async def on_data(self, sender, data):
        sep()
        for tr in data:
            print(f'{self.tag}:  {tr}')

    def __init__(self, tag=''):
        self.tag = tag


async def t_tx_scanner(url, reserve_address):
    scanner = NativeScannerTX(url)
    detector = RuneTransferDetectorFromTxResult(reserve_address)
    scanner.subscribe(detector)
    # scanner.subscribe(Receiver('TX'))
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
    reserve_address = cfg.as_str('native_scanner.reserve_address')
    await t_tx_scanner(url, reserve_address)


if __name__ == '__main__':
    setup_logs(logging.INFO)
    asyncio.run(main())
