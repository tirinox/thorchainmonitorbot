import asyncio
import json
import logging

from services.jobs.fetch.native_scan import NativeScannerBlock, NativeScannerBlockResults, NativeScannerTx
from services.jobs.fetch.native_scan_ws import NativeScannerTransactionWS, NativeScannerBlockEventsWS
from services.jobs.transfer_detector import RuneTransferDetectorBlockEvents, \
    RuneTransferDetectorFromTxResult
from services.lib.config import Config
from services.lib.delegates import INotified
from services.lib.texts import sep
from services.lib.utils import setup_logs
from tools.lib.lp_common import LpAppFramework


class Receiver(INotified):
    # noinspection PyTypeChecker
    async def on_data(self, sender, data):
        sep()
        items, block_no = data
        for tr in items:
            if not self.filters or any(text in repr(tr) for text in self.filters):
                print(f'{self.tag} @ {block_no}:  {tr}')

    def __init__(self, tag='', filters=None):
        self.tag = tag
        self.filters = filters


async def t_tx_scanner(url, reserve_address):
    scanner = NativeScannerTransactionWS(url)
    detector = RuneTransferDetectorFromTxResult(reserve_address)
    scanner.subscribe(detector)
    # scanner.subscribe(Receiver('TX'))
    detector.subscribe(Receiver('Transfer'))
    await scanner.run()


async def t_block_scanner(url):
    scanner = NativeScannerBlockEventsWS(url)
    detector = RuneTransferDetectorBlockEvents()
    scanner.subscribe(detector)
    detector.subscribe(Receiver())
    await scanner.run()


async def ws_main():
    cfg = Config()
    url = cfg.as_str('thor.node.rpc_node_url')
    reserve_address = cfg.as_str('native_scanner.reserve_address')
    await t_tx_scanner(url, reserve_address)


async def ws_active_scan(lp_app):
    scanner = NativeScannerBlock(lp_app.deps, sleep_period=7)
    scanner.subscribe(Receiver('EV'))
    await scanner.run()


async def active_one(lp_app):
    # b = 6169406  # me send
    b = 6187632
    scanner = NativeScannerBlockResults(lp_app.deps)
    r = await scanner.fetch_block_results(b)
    if r:
        for ev in r:
            events = ev[0]['events']
            # print(events)
            n = len(events)
            types = [e['type'] for e in events]
            print(f'{n} events: {", ".join(types)}')
            if n > 1:
                print(json.dumps(events, indent=2))

    sep()
    #
    # scanner = NativeScannerTx(lp_app.deps)
    # r = await scanner.fetch_block_txs(b)
    # if r:
    #     for ev in r:
    #         print(ev)


async def main():
    lp_app = LpAppFramework(log_level=logging.INFO)
    async with lp_app(brief=True):
        await active_one(lp_app)
    # [
    #                          'MsgDeposit',
    #                          'MsgSend',
    #                          'MsgWithdraw',
    #                          'MsgDonate'
    #                      ]


if __name__ == '__main__':
    setup_logs(logging.INFO)
    asyncio.run(main())
