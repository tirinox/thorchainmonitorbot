import asyncio
import json
import pickle

from localization.eng_base import BaseLocalization
from localization.languages import Language
from services.jobs.scanner.native_scan import NativeScannerBlock
from services.jobs.transfer_detector import RuneTransferDetectorTxLogs
from services.lib.delegates import INotified
from services.lib.depcont import DepContainer
from services.lib.texts import sep
from services.models.transfer import RuneTransfer
from services.notify.personal.balance import PersonalBalanceNotifier
from services.notify.types.transfer_notify import RuneMoveNotifier
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


async def demo_native_block_action_detector(app, start=12209517):
    scanner = NativeScannerBlock(app.deps, last_block=start)
    scanner.one_block_per_run = True
    detector = RuneTransferDetectorTxLogs()
    scanner.add_subscriber(detector)
    detector.add_subscriber(Receiver('Transfer'))
    # action_extractor = NativeActionExtractor(app.deps)
    # scanner.add_subscriber(action_extractor)
    # action_extractor.add_subscriber(Receiver('Action'))
    await scanner.run_once()


# sic!
async def demo_block_scanner_active(app, send_alerts=False, catch_up=False):
    scanner = NativeScannerBlock(app.deps)
    detector = RuneTransferDetectorTxLogs()
    scanner.add_subscriber(detector)
    detector.add_subscriber(Receiver('Transfer'))

    if catch_up:
        await scanner.ensure_last_block()
        scanner.last_block -= 30

    if send_alerts:
        notifier = RuneMoveNotifier(app.deps)
        detector.add_subscriber(notifier)
        notifier.add_subscriber(app.deps.alert_presenter)
    await scanner.run()


async def get_transfers_from_block(app, block_index):
    scanner = NativeScannerBlock(app.deps)
    r = await scanner.fetch_one_block(block_index)
    parser = RuneTransferDetectorTxLogs()
    transfers = parser.process_events(r)
    return transfers


async def demo_rune_transfers_once(app, block=12_918_080):
    transfers = await get_transfers_from_block(app, block)

    sep()
    for tr in transfers:
        print(tr)
    sep()

    notifier = RuneMoveNotifier(app.deps)
    notifier.add_subscriber(app.deps.alert_presenter)
    await notifier.on_data(None, transfers)

    await asyncio.sleep(3.0)


async def search_out(app):
    scanner = NativeScannerBlock(app.deps)

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


async def get_block_cached(app, block_index):
    filename = f'../temp/block_results_{block_index}.pickle'
    try:
        with open(filename, 'rb') as f:
            block = pickle.load(f)
    except FileNotFoundError:
        scanner = NativeScannerBlock(app.deps)
        block = await scanner.fetch_one_block(block_index)
        with open(filename, 'wb') as f:
            pickle.dump(block, f)

    return block


async def debug_block_tx_status_check(app):
    block = await get_block_cached(app, 12706550)
    print(block)


async def demo_debug_personal_transfer(app):
    balance_notifier = PersonalBalanceNotifier(app.deps)
    await balance_notifier.on_data(None, [
        RuneTransfer(
            'thor136askulc04d0ek9yra6860vsaaamequv2l0jwh',
            'thor1tcet6mxe80x89a8dlpynehlj4ya7cae4v3hmce',
            13_300_000, '9E29B0D4E356DBA2B865AB129E22C4FA905C4720B3CCCAF7E0B2E0F4D9BDCF31',
            3456.78, 2.99, is_native=True, comment='Send', memo='Hello, world!'
        )
    ])
    await asyncio.sleep(3.0)


async def demo_non_zero_code(app: LpAppFramework):
    # bad_block = 13424040

    # 💸 Large transfer  "Send": 102.5M Rune ᚱ ($608,499,689) from thor1zw...6s66 ➡️ Binance Hot.
    bad_block = 13_480_048
    transfers = await get_transfers_from_block(app, bad_block)
    print(transfers)
    assert all(t for t in transfers if t.amount < 1_000_000)


async def main():
    app = LpAppFramework()
    async with app(brief=True):
        # await demo_non_zero_code(app)
        # await demo_block_scanner_active(app, send_alerts=False, catch_up=True)

        # await demo_debug_personal_transfer(app)

        # await search_out(app)

        # await demo_test_rune_detector(app)
        # await demo_native_block_action_detector(app)

        # await debug_block_tx_status_check(app)
        await demo_rune_transfers_once(app, block=13670768)


if __name__ == '__main__':
    asyncio.run(main())
