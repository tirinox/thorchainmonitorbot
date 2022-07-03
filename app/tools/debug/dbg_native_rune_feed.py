import asyncio
import json
import logging

from services.jobs.fetch.native_scan import NativeScannerBlock
from services.jobs.fetch.native_scan_ws import NativeScannerTransactionWS, NativeScannerBlockEventsWS
from services.jobs.transfer_detector import RuneTransferDetectorBlockEvents, \
    RuneTransferDetectorFromTxResult, RuneTransferDetectorTxLogs
from services.lib.config import Config
from services.lib.delegates import INotified
from services.lib.texts import sep
from services.lib.utils import setup_logs
from tools.lib.lp_common import LpAppFramework


class Receiver(INotified):
    # noinspection PyTypeChecker
    async def on_data(self, sender, data):
        sep()
        for tr in data:
            if not self.filters or any(text in repr(tr) for text in self.filters):
                print(f'{self.tag}:  {tr}')

    def __init__(self, tag='', filters=None):
        self.tag = tag
        self.filters = filters


async def t_tx_scanner_ws(url, reserve_address):
    scanner = NativeScannerTransactionWS(url)
    detector = RuneTransferDetectorFromTxResult(reserve_address)
    scanner.subscribe(detector)
    # scanner.subscribe(Receiver('TX'))
    detector.subscribe(Receiver('Transfer'))
    await scanner.run()


async def t_block_scanner_ws(url):
    scanner = NativeScannerBlockEventsWS(url)
    detector = RuneTransferDetectorBlockEvents()
    scanner.subscribe(detector)
    detector.subscribe(Receiver())
    await scanner.run()


async def t_block_scanner_active(lp_app):
    scanner = NativeScannerBlock(lp_app.deps)
    detector = RuneTransferDetectorTxLogs()
    scanner.subscribe(detector)
    detector.subscribe(Receiver('Transfer'))
    await scanner.run()


async def ws_main():
    cfg = Config()
    url = cfg.as_str('thor.node.rpc_node_url')
    reserve_address = cfg.as_str('native_scanner.reserve_address')
    await t_tx_scanner_ws(url, reserve_address)



async def active_one(lp_app):
    # b = 6237587  # send: https://viewblock.io/thorchain/tx/34A4B4885E7E42AB2FBB7F3EA950D1795B19CB5715862487F8320E4FA1B9E61C
    # b = 6235520  # withdraw: https://viewblock.io/thorchain/tx/16F5ABB456FEA325B47F1E2EE984FEA39344F56432F474A73BC3AC2E02E7379D
    # b = 6187632
    # b = 6240682  # synth send
    b = 6230655  # synth mint 9E7D7BE18EC0CFC13D9AC45A76EB9F5923EF4F1CC49299E2346E613EA144ADEE
    scanner = NativeScannerBlock(lp_app.deps)
    r = await scanner.fetch_block_results(b)
    r.txs = await scanner.fetch_block_txs(b)
    parser = RuneTransferDetectorTxLogs()
    transfers = parser.process_events(r)

    sep()
    for tr in transfers:
        print(tr)
        # for ev in r:
        #     events = ev[0]['events']
        #     # print(events)
        #     n = len(events)
        #     types = [e['type'] for e in events]
        #     print(f'{n} events: {", ".join(types)}')
        #     if n > 1:
        #         print(json.dumps(events, indent=2))

    sep()
    #
    # scanner = NativeScannerTx(lp_app.deps)
    # r = await scanner.fetch_block_txs(b)
    # if r:
    #     for ev in r:
    #         print(ev)


async def search_out(lp_app):
    scanner = NativeScannerBlock(lp_app.deps)

    block_start = 6230655 - 2
    search = '687522'

    b = block_start
    while True:
        tx_logs = await scanner.fetch_block_results(b)
        if search in json.dumps(tx_logs):
            print(tx_logs)
            print(f'Found a needle in block #{b}!!! ')
            break
        b += 1



async def main():
    lp_app = LpAppFramework(log_level=logging.INFO)
    async with lp_app(brief=True):
        await t_block_scanner_active(lp_app)
        # await active_one(lp_app)
        # await search_out(lp_app)


if __name__ == '__main__':
    setup_logs(logging.INFO)
    asyncio.run(main())
