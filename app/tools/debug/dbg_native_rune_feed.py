import asyncio
import logging
import pickle

from comm.localization.eng_base import BaseLocalization
from comm.localization.languages import Language
from jobs.scanner.native_scan import BlockScanner
from jobs.scanner.transfer_detector import RuneTransferDetector
from lib.delegates import INotified
from lib.depcont import DepContainer
from lib.texts import sep
from models.transfer import NativeTokenTransfer
from notify.personal.balance import PersonalBalanceNotifier
from notify.public.transfer_notify import RuneMoveNotifier
from tools.lib.lp_common import LpAppFramework, Receiver


class ReceiverPublicText(INotified):
    def __init__(self, deps: DepContainer, lang=Language.ENGLISH_TWITTER):
        self.deps = deps
        self.loc: BaseLocalization = self.deps.loc_man.get_from_lang(lang)

    # noinspection PyTypeChecker
    async def on_data(self, sender, data):
        for tr in data:
            tr: NativeTokenTransfer
            print(self.loc.notification_text_rune_transfer_public(tr, {}))
            sep()


async def demo_native_block_action_detector(app, start=12209517):
    scanner = BlockScanner(app.deps, last_block=start)
    scanner.one_block_per_run = True
    detector = RuneTransferDetector()
    scanner.add_subscriber(detector)
    detector.add_subscriber(Receiver('Transfer'))
    # action_extractor = NativeActionExtractor(app.deps)
    # scanner.add_subscriber(action_extractor)
    # action_extractor.add_subscriber(Receiver('Action'))
    await scanner.run_once()


# sic!
async def demo_block_scanner_active(app, send_alerts=False, catch_up=0, force_start_block=None,
                                    print_txs=False):
    d = app.deps
    # scanner = BlockScanner(d, sleep_period=10.0)
    scanner = BlockScanner(d)
    detector = RuneTransferDetector()
    scanner.add_subscriber(detector)

    if print_txs:
        detector.add_subscriber(Receiver('Transfer'))

    if catch_up:
        await scanner.ensure_last_block()
        scanner.last_block -= catch_up
    elif force_start_block:
        scanner.last_block = force_start_block

    if send_alerts:
        notifier = RuneMoveNotifier(app.deps)
        notifier.min_usd_native = 0.1
        detector.add_subscriber(notifier)
        notifier.add_subscriber(app.deps.alert_presenter)
    await scanner.run()


async def get_transfers_from_block(app, block_index):
    scanner = BlockScanner(app.deps)
    r = await scanner.fetch_one_block(block_index)
    parser = RuneTransferDetector()
    transfers = await parser.process_block(r)
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


async def get_block_cached(app, block_index):
    filename = f'../temp/block_results_{block_index}.pickle'
    try:
        with open(filename, 'rb') as f:
            block = pickle.load(f)
    except FileNotFoundError:
        scanner = BlockScanner(app.deps)
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
        NativeTokenTransfer(
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


async def debug_ill_transfers(app: LpAppFramework):
    block_id = 15264091

    scanner = BlockScanner(app.deps, last_block=block_id)
    block = await scanner.fetch_one_block(block_id)
    detector = RuneTransferDetector()
    events = detector.process_block(block)
    print(events)


async def dbg_second_chance_before_deactivate(app):
    bpt = PersonalBalanceNotifier(app.deps)
    addr = "thor1zslq29e77hqsjfklprnwaf0a29zcnxlpp3fc2u"
    while True:
        await bpt.group_and_send_messages(
            [addr],
            [
                NativeTokenTransfer(addr, addr, 1230000, "FFFFFFFFFFF", 300.123, 5.0, is_native=True,
                                    memo="foobar", comment="comment")
            ]
        )
        await asyncio.sleep(10.0)


BLOCK_UNBOND = 19027130
BLOCK_BOND = 18986273
BLOCK_SEND = 19034147
BLOCK_RUJI_SEND = 21600000


async def main():
    app = LpAppFramework(log_level=logging.INFO)
    async with app(brief=True):
        await demo_block_scanner_active(app, send_alerts=True, catch_up=500)
        # await demo_rune_transfers_once(app, BLOCK_BOND)
        # await demo_rune_transfers_once(app, BLOCK_UNBOND)
        # await demo_debug_personal_transfer(app)
        # await demo_rune_transfers_once(app, BLOCK_RUJI_SEND)
        await asyncio.sleep(3.0)


if __name__ == '__main__':
    asyncio.run(main())
