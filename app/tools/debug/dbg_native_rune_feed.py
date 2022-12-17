import asyncio
import json
import logging
from collections import Counter

from localization.eng_base import BaseLocalization
from localization.languages import Language
from services.jobs.fetch.native_scan import NativeScannerBlock
from services.jobs.fetch.native_scan_ws import NativeScannerTransactionWS, NativeScannerBlockEventsWS
from services.jobs.native_actions import NativeActionExtractor
from services.jobs.transfer_detector import RuneTransferDetectorBlockEvents, \
    RuneTransferDetectorFromTxResult, RuneTransferDetectorTxLogs
from services.lib.config import Config
from services.lib.delegates import INotified
from services.lib.depcont import DepContainer
from services.lib.texts import sep
from services.models.transfer import RuneTransfer
from tests.test_rune_transfer import find_transfer
from tools.lib.lp_common import LpAppFramework, Receiver


class ReceiverPublicText(INotified):
    def __init__(self, deps: DepContainer, lang=Language.ENGLISH_TWITTER):
        self.deps = deps
        self.loc: BaseLocalization = self.deps.loc_man.get_from_lang(lang)

    # noinspection PyTypeChecker
    async def on_data(self, sender, data):
        for tr in data:
            tr: RuneTransfer
            print(self.loc.notification_text_rune_transfer_public(tr, {}))
            sep()


async def t_tx_scanner_ws(url, reserve_address):
    scanner = NativeScannerTransactionWS(url)
    detector = RuneTransferDetectorFromTxResult(reserve_address)
    scanner.add_subscriber(detector)
    # scanner.subscribe(Receiver('TX'))
    detector.add_subscriber(Receiver('Transfer'))
    await scanner.run()


async def t_block_scanner_ws(url):
    scanner = NativeScannerBlockEventsWS(url)
    detector = RuneTransferDetectorBlockEvents()
    scanner.add_subscriber(detector)
    detector.add_subscriber(Receiver())
    await scanner.run()


# sic!
async def t_block_scanner_active(lp_app):
    scanner = NativeScannerBlock(lp_app.deps)
    detector = RuneTransferDetectorTxLogs()
    scanner.add_subscriber(detector)
    detector.add_subscriber(Receiver('Transfer'))
    # detector.subscribe(ReceiverPublicText(lp_app.deps))

    action_extractor = NativeActionExtractor(lp_app.deps)
    scanner.add_subscriber(action_extractor)

    action_extractor.add_subscriber(Receiver('Action'))

    await scanner.run()


async def t_block_scanner_once(lp_app):
    # block_index = 7276413  # guaranteed to have DEX tx
    # block_index = 7326235  # guaranteed to have Swap In
    # block_index = 6_999_399  # Timestamp Aug.23.2022 01:44:57
    # block_index = 6999486  # a bit later
    block_index = 8665175  # bond

    scanner = NativeScannerBlock(lp_app.deps)

    action_extractor = NativeActionExtractor(lp_app.deps)
    scanner.add_subscriber(action_extractor)
    action_extractor.add_subscriber(Receiver('Action'))

    block = await scanner.fetch_one_block(block_index)

    c = Counter([
        tx.first_message.__class__.__name__ for tx in block.txs
    ])

    print(c)

    watch_cache = {
        '05E35D53F0AD7C56CCB0CDA353CA3F46D5789D81DDCD42ED26716DFDC5B64EF9',
        'D45F100F3F48C786720167F5705B9D6736C195F028B5293FE93159DF923DE7C7',
        '16F31635F6AF333ACE4F4BF5931674CCC35A3D5332CD03223B95897E1F537195',
        'D4A7CCD5AF8BBA56C1CD473FBBCB337F4AF8CFD757E4D627EA2197A95DD5110A'
    }

    for tx in block.txs:
        if tx.hash in watch_cache:
            print(f"{tx.hash} => {tx}")

    await action_extractor.on_data(scanner, block)


async def ws_main():
    cfg = Config()
    url = cfg.as_str('thor.node.rpc_node_url')
    reserve_address = cfg.as_str('native_scanner.reserve_address')
    await t_tx_scanner_ws(url, reserve_address)


async def get_transfers_from_block(app, block_index):
    scanner = NativeScannerBlock(app.deps)
    r = await scanner.fetch_one_block(block_index)
    parser = RuneTransferDetectorTxLogs()
    transfers = parser.process_events(r)
    return transfers


async def demo_test_rune_detector(app):
    transfers = await get_transfers_from_block(app, 8686879)
    assert find_transfer(transfers, rune_amount=100000)


async def demo_rune_transfers_once(lp_app):
    # b = 6237587  # send: https://viewblock.io/thorchain/tx/34A4B4885E7E42AB2FBB7F3EA950D1795B19CB5715862487F8320E4FA1B9E61C
    # b = 6235520  # withdraw: https://viewblock.io/thorchain/tx/16F5ABB456FEA325B47F1E2EE984FEA39344F56432F474A73BC3AC2E02E7379D
    # b = 6187632
    # b = 6240682  # synth send
    # b = 6230655  # synth mint 9E7D7BE18EC0CFC13D9AC45A76EB9F5923EF4F1CC49299E2346E613EA144ADEE
    # b = 8665175  # bond
    # b = 8217619  # memo mess
    # b = 8685981  # memo mess 2
    b = 8686879  # send with memo
    transfers = await get_transfers_from_block(lp_app, b)

    sep()
    for tr in transfers:
        print(tr)

    sep()

    # notifier = RuneMoveNotifier(lp_app.deps)
    # await notifier.on_data(None, transfers)


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
        # await t_block_scanner_active(lp_app)
        # await t_block_scanner_once(lp_app)
        # await active_one(lp_app)
        # await search_out(lp_app)
        # await demo_rune_transfers_once(lp_app)
        await demo_test_rune_detector(lp_app)


if __name__ == '__main__':
    asyncio.run(main())
