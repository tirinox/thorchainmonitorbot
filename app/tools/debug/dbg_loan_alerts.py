import asyncio
import copy
import random
from pprint import pprint

from comm.localization.eng_base import BaseLocalization
from jobs.fetch.lending_stats import LendingStatsFetcher
from jobs.runeyield.borrower import BorrowerPositionGenerator
from jobs.scanner.event_db import EventDatabase
from jobs.scanner.loan_extractor import LoanExtractorBlock
from jobs.scanner.native_scan import BlockScanner
from lib.money import DepthCurve
from lib.texts import sep
from lib.utils import load_pickle, save_pickle
from lib.var_file import var_file_loop
from models.loans import AlertLendingStats, LendingStats
from notify.public.lend_stats_notify import LendingStatsNotifier
from notify.public.lending_open_up import LendingCapsNotifier
from notify.public.loans_notify import LoanTxNotifier
from tools.lib.lp_common import LpAppFramework


async def dbg_lending_limits(app: LpAppFramework):
    await asyncio.gather(
        app.deps.rune_market_fetcher.run_once(),
        app.deps.pool_fetcher.run_once(),
        app.deps.mimir_const_fetcher.run_once(),
    )

    borrowers_fetcher = LendingStatsFetcher(app.deps)

    results = await borrowers_fetcher.fetch()
    pprint(results)


async def debug_block_analyse(app: LpAppFramework, block_no):
    scanner = BlockScanner(app.deps)
    # await scanner.run()
    blk = await scanner.fetch_one_block(block_no)
    print(blk)
    sep()



async def debug_full_pipeline(app, start=None, tx_id=None, single_block=False):
    d = app.deps

    # Block scanner: the source of the river
    d.block_scanner = BlockScanner(d, last_block=start)
    d.block_scanner.one_block_per_run = single_block
    d.block_scanner.allow_jumps = False

    # Swap notifier (when it finishes)
    curve_pts = d.cfg.get_pure('tx.curve', default=DepthCurve.DEFAULT_TX_VS_DEPTH_CURVE)
    curve = DepthCurve(curve_pts)

    loan_extractor = LoanExtractorBlock(d)
    d.block_scanner.add_subscriber(loan_extractor)

    loan_notifier = LoanTxNotifier(d, curve=curve)
    loan_extractor.add_subscriber(loan_notifier)
    loan_notifier.add_subscriber(d.alert_presenter)
    await loan_notifier.deduplicator.clear()

    # Run all together
    if single_block:
        await d.block_scanner.run_once()
    else:
        while True:
            await d.block_scanner.run()
            await asyncio.sleep(5.9)


async def debug_tx_records(app: LpAppFramework, tx_id):
    ev_db = EventDatabase(app.deps.db)

    props = await ev_db.read_tx_status(tx_id)
    sep('swap')
    print(props)

    sep('tx')
    tx = props.build_action()
    print(tx)


async def demo_lending_stats_with_deltas(app: LpAppFramework):
    await asyncio.gather(
        app.deps.pool_fetcher.run_once(),
        app.deps.rune_market_fetcher.run_once(),
        app.deps.mimir_const_fetcher.run_once(),
    )

    borrowers_fetcher = LendingStatsFetcher(app.deps)

    notifier = LendingStatsNotifier(app.deps)
    notifier.add_subscriber(app.deps.alert_presenter)

    await notifier.cd.clear()

    borrowers_fetcher.add_subscriber(notifier)

    await borrowers_fetcher.run_once()

    await asyncio.sleep(5)


LENDING_STATS_SAVED_FILE = '../temp/lending_stats_v2.pkl'


async def _preload(app):
    await app.deps.pool_fetcher.run_once()
    await app.deps.last_block_fetcher.run_once()
    await app.deps.rune_market_fetcher.fetch()
    await app.deps.mimir_const_fetcher.run_once()


async def demo_lending_stats(app: LpAppFramework, cached=False):
    if cached:
        data = load_pickle(LENDING_STATS_SAVED_FILE)
    else:
        data = None

    if not data or not isinstance(data, AlertLendingStats):
        print('No saved data. Will load...')

        await _preload(app)

        borrowers_fetcher = LendingStatsFetcher(app.deps)
        data = await borrowers_fetcher.fetch()

        prev = copy.deepcopy(data)

        prev: LendingStats = prev._replace(
            rune_burned_rune=prev.rune_burned_rune + random.uniform(-100000, 10000000),
        )

        data = AlertLendingStats(data, prev)
        if cached:
            save_pickle(LENDING_STATS_SAVED_FILE, data)

    await app.test_all_locs(
        BaseLocalization.notification_lending_stats, None, data
    )


async def demo_personal_loan_card(app: LpAppFramework):
    gen = BorrowerPositionGenerator(app.deps)
    # pool = 'BTC.BTC'
    pool = 'ETH.ETH'
    # address = 'bc1q8087yq4x9j4zyp4nua9ex7yrjf8h6kajdzrepp'  # didn't repay dept
    # address = 'bc1qcsn8nwh7aqj3swx5ryps42y89fftxv08la3cyw'  # repaid dept
    address = '0xf744112774ef03c8d35f8d1f5b4677933fbd3d6b'

    card = await gen.get_loan_report_card(pool, address)

    print(card)

    await app.test_locs_except_tw(
        BaseLocalization.notification_text_loan_card,
        card,
        'mockWallet',
        '12345'
    )


async def demo_lending_opened_up(app: LpAppFramework):
    await _preload(app)

    data = load_pickle(LENDING_STATS_SAVED_FILE)
    if not data or not isinstance(data, AlertLendingStats):
        print('No saved data. It is impossible to run this demo without the saved data.')
        return

    notifier = LendingCapsNotifier(app.deps)
    notifier.add_subscriber(app.deps.alert_presenter)

    var_data = copy.deepcopy(data)

    async def var_changed(_prev, curr):
        var_data.current.pools[0] = var_data.current.pools[0]._replace(
            collateral_available=curr.get('collateral_available', 0),
            fill=curr.get('fill', 101) / 100.0
        )

    async def every_tick(_):
        await notifier.on_data(None, var_data.current)

    await var_file_loop(var_changed, 3.0)


async def run():
    app = LpAppFramework()
    async with app(brief=True):
        # await demo_personal_loan_card(app)

        await demo_lending_stats(app, cached=True)
        # await demo_lending_stats_with_deltas(app)
        # await dbg_lending_limits(app)
        await demo_lending_opened_up(app)

        # await debug_block_analyse(app, 12262380)
        # await debug_tx_records(app, 'xxx')
        # await debug_full_pipeline(
        #     app,
        #     start=12258889,
        #     # tx_id='xx',
        #     # single_block=True
        # )


if __name__ == '__main__':
    asyncio.run(run())
