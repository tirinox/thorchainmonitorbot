import asyncio
import json

from jobs.fetch.ruji_merge import RujiMergeStatsFetcher
from jobs.ruji_merge import RujiMergeTracker
from jobs.scanner.native_scan import BlockScanner
from lib.constants import THOR_BLOCK_TIME
from lib.date_utils import now_ts, DAY
from lib.texts import sep
from lib.utils import namedtuple_to_dict
from models.ruji import AlertRujiraMergeStats
from notify.channel import BoardMessage, MessageType
from notify.public.ruji_merge_stats import RujiMergeStatsTxNotifier
from tools.lib.lp_common import LpAppFramework, Receiver


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

    ruji_merge_tracker.add_subscriber(Receiver("Ruji merge"))

    top_txs = await ruji_merge_tracker.get_top_events_from_db(now_ts(), 7, limit=10)
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

    top_txs_days_back = 10
    merge_stats = await ruji_merge_tracker.get_merge_system()
    top_txs = await ruji_merge_tracker.get_top_events_from_db(now_ts(), top_txs_days_back)

    sep("Stats")
    print(merge_stats)
    print_top_merges(top_txs)

    sep()
    alert = AlertRujiraMergeStats(merge_stats, top_txs, top_txs_days_back=top_txs_days_back)
    print(json.dumps(namedtuple_to_dict(alert), indent=4))
    sep()


async def demo_ruji_stats_continuous(app):
    d = app.deps

    ruji_stats_fetcher = RujiMergeStatsFetcher(d)
    ruji_stats_fetcher.initial_sleep = 0

    notifier_ruji_merge = RujiMergeStatsTxNotifier(d)
    notifier_ruji_merge.stats_days_back = 7
    notifier_ruji_merge.add_subscriber(d.alert_presenter)
    ruji_stats_fetcher.add_subscriber(notifier_ruji_merge)

    await ruji_stats_fetcher.run()


async def demo_send_merge_stats_pic_once(app):
    ruji_merge_tracker = RujiMergeTracker(app.deps)
    merge = await ruji_merge_tracker.get_merge_system()
    top_txs = await ruji_merge_tracker.get_top_events_from_db(now_ts(), 1)
    event = AlertRujiraMergeStats(merge, top_txs, 1)

    text = app.deps.loc_man.default.notification_rujira_merge_stats(event)
    photo, photo_name = await app.deps.alert_presenter.render_rujira_merge_graph(None, event)

    await app.deps.broadcaster.broadcast_to_all(BoardMessage.make_photo(photo, text, photo_name))


async def run():
    app = LpAppFramework()
    async with app(brief=True):
        # await dbg_switch_event_continuous(app, force_start_block=20852630, one_block=True)
        # await dbg_get_merge_status(app)
        # await dbg_switch_event_continuous(app, force_start_block=20852470 - int(DAY / THOR_BLOCK_TIME))
        # await dbg_mering_coin_gecko_prices(app)
        await demo_ruji_stats_continuous(app)
        # await demo_send_merge_stats_pic_once(app)


if __name__ == '__main__':
    asyncio.run(run())
