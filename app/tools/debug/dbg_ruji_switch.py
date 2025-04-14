import asyncio
import json

from jobs.fetch.ruji_merge import RujiMergeStatsFetcher
from jobs.ruji_merge import RujiMergeTracker
from jobs.scanner.native_scan import BlockScanner
from lib.date_utils import now_ts
from lib.texts import sep
from lib.utils import namedtuple_to_dict
from models.ruji import AlertRujiraMergeStats
from tools.lib.lp_common import LpAppFramework


def print_top_merges(top_txs):
    sep('top merge')
    for place, tx in enumerate(top_txs, start=1):
        print(f"#{place}: {tx.amount} {tx.asset} {tx.tx_id} ({tx.from_address}) {tx.volume_usd:.2f} USD")
    sep()


async def dbg_switch_event_continuous(app: LpAppFramework, force_start_block=None, catch_up=0, one_block=False):
    d = app.deps
    d.block_scanner = BlockScanner(d)
    d.block_scanner.initial_sleep = 0

    await d.pool_fetcher.run_once()
    d.last_block_fetcher.add_subscriber(d.last_block_store)
    await d.last_block_fetcher.run_once()

    ruji_merge_tracker = RujiMergeTracker(d)
    d.block_scanner.add_subscriber(ruji_merge_tracker)

    # ruji_switch_decoder.add_subscriber(Receiver("switch"))

    top_txs = await ruji_merge_tracker.get_top_events_from_db(now_ts(), 5)
    print_top_merges(top_txs)

    if catch_up > 0:
        await d.block_scanner.ensure_last_block()
        d.block_scanner.last_block -= catch_up
    elif force_start_block:
        d.block_scanner.last_block = force_start_block

    if one_block:
        d.block_scanner.one_block_per_run = True
        await d.block_scanner.run_once()
    else:
        await d.block_scanner.run()


async def dbg_merging_coin_gecko_prices(app):
    f = RujiMergeStatsFetcher(app.deps)
    prices = await f.get_prices_usd_from_gecko()
    print(prices)


async def dbg_get_merge_status(app):
    ruji_merge_tracker = RujiMergeTracker(app.deps)

    merge_stats = await ruji_merge_tracker.get_merge_system()
    top_txs = await ruji_merge_tracker.get_top_events_from_db(now_ts(), 10)

    sep("Stats")
    print(merge_stats)
    print_top_merges(top_txs)

    sep()
    alert = AlertRujiraMergeStats(merge_stats, top_txs)
    print(json.dumps(namedtuple_to_dict(alert), indent=4))
    sep()


async def run():
    app = LpAppFramework()
    async with app(brief=True):
        # await dbg_switch_event_continuous(app, force_start_block=20639916)
        await dbg_get_merge_status(app)
        await dbg_switch_event_continuous(app, force_start_block=20698109 - 1200)
        # await dbg_mering_coin_gecko_prices(app)
        #


if __name__ == '__main__':
    asyncio.run(run())
