import asyncio
import logging

from services.dialog.picture.price_picture import price_graph_from_db
from services.jobs.fetch.gecko_price import fill_rune_price_from_gecko
from services.jobs.fetch.pool_price import PoolFetcher
from services.jobs.fetch.tx import TxFetcher
from services.jobs.scanner.native_scan import NativeScannerBlock
from services.jobs.scanner.swap_extractor import SwapExtractorBlock
from services.jobs.scanner.trade_acc import TradeAccEventDecoder
from services.jobs.volume_filler import VolumeFillerUpdater
from services.jobs.volume_recorder import VolumeRecorder, TxCountRecorder
from services.lib.depcont import DepContainer
from services.lib.draw_utils import save_image_and_show
from services.lib.w3.aggregator import AggregatorDataExtractor
from services.models.memo import ActionType
from services.notify.types.price_notify import PriceNotifier
from tools.debug.dbg_discord import debug_prepare_discord_bot
from tools.debug.dbg_supply_graph import debug_get_rune_market_data
from tools.lib.lp_common import LpAppFramework, Receiver


async def continuous_volume_recording(lp_app):
    d: DepContainer = lp_app.deps

    d.pool_fetcher = PoolFetcher(d)
    await d.pool_fetcher.run_once()
    await d.mimir_const_fetcher.run_once()
    await d.last_block_fetcher.run_once()

    main_tx_types = [
        # ThorTxType.TYPE_SWAP,
        ActionType.REFUND,
        ActionType.ADD_LIQUIDITY,
        ActionType.WITHDRAW,
        ActionType.DONATE
    ]

    # Uses Midgard as data source
    fetcher_tx = TxFetcher(d, tx_types=main_tx_types)

    aggregator = AggregatorDataExtractor(d)
    fetcher_tx.add_subscriber(aggregator)

    d.block_scanner = NativeScannerBlock(d, max_attempts=3)
    native_action_extractor = SwapExtractorBlock(d)
    d.block_scanner.add_subscriber(native_action_extractor)

    native_action_extractor.add_subscriber(aggregator)

    volume_filler = VolumeFillerUpdater(d)
    aggregator.add_subscriber(volume_filler)

    d.volume_recorder = VolumeRecorder(d)
    volume_filler.add_subscriber(d.volume_recorder)

    d.tx_count_recorder = TxCountRecorder(d)
    volume_filler.add_subscriber(d.tx_count_recorder)

    # Count Trade deposits and withdrawals
    traed = TradeAccEventDecoder(d.db, d.price_holder)
    d.block_scanner.add_subscriber(traed)
    traed.add_subscriber(d.volume_recorder)
    traed.add_subscriber(d.tx_count_recorder)

    async def cb(*args):
        print('tick')

    receiver = Receiver(d, callback=cb)
    volume_filler.add_subscriber(receiver)

    await asyncio.gather(
        fetcher_tx.run(),
        d.block_scanner.run(),
        d.pool_fetcher.run(),
        d.last_block_fetcher.run(),
    )


async def make_price_graph(lp_app, fill=False):
    if fill:
        await fill_rune_price_from_gecko(lp_app.deps.db, include_fake_det=True)
    loc = lp_app.deps.loc_man.default
    return await price_graph_from_db(lp_app.deps, loc)


async def debug_post_price_graph_to_discord(app: LpAppFramework):
    # graph, graph_name = await make_price_graph(app)
    await debug_prepare_discord_bot(app)

    sender = PriceNotifier(app.deps)
    hist_prices = await sender.historical_get_triplet()

    net_stats, market_info = await debug_get_rune_market_data(app)

    await sender.do_notify_price_table(market_info, hist_prices, ath=False)


async def demo_show_price_graph(app: LpAppFramework):
    graph, graph_name = await make_price_graph(app)
    save_image_and_show(graph, '../temp/price_gr.png')


async def main():
    app = LpAppFramework(log_level=logging.INFO)
    async with app(brief=True):
        await continuous_volume_recording(app)
        # await demo_show_price_graph(app)
        # await debug_post_price_graph_to_discord(app)


if __name__ == '__main__':
    asyncio.run(main())
