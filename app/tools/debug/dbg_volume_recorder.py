import asyncio
import logging

from api.w3.aggregator import AggregatorDataExtractor
from jobs.fetch.pool_price import PoolFetcher
from jobs.fetch.tx import TxFetcher
from jobs.scanner.native_scan import BlockScanner
from jobs.scanner.swap_extractor import SwapExtractorBlock
from jobs.scanner.trade_acc import TradeAccEventDecoder
from jobs.volume_filler import VolumeFillerUpdater
from lib.date_utils import now_ts, DAY
from lib.depcont import DepContainer
from models.memo import ActionType
from tools.lib.lp_common import LpAppFramework, Receiver


async def continuous_volume_recording(lp_app):
    d: DepContainer = lp_app.deps

    d.pool_fetcher = PoolFetcher(d)

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

    last_block = await d.last_block_cache.get_thor_block()
    d.block_scanner = BlockScanner(d, max_attempts=3, last_block=last_block - 1000, role='debug')
    
    native_action_extractor = SwapExtractorBlock(d)
    d.block_scanner.add_subscriber(native_action_extractor)

    native_action_extractor.add_subscriber(aggregator)

    volume_filler = VolumeFillerUpdater(d)
    aggregator.add_subscriber(volume_filler)

    volume_filler.add_subscriber(d.volume_recorder)
    volume_filler.add_subscriber(d.tx_count_recorder)

    # Count Trade deposits and withdrawals
    traed = TradeAccEventDecoder(d.pool_cache)
    d.block_scanner.add_subscriber(traed)
    traed.add_subscriber(d.volume_recorder)
    traed.add_subscriber(d.tx_count_recorder)

    async def cb(*args):
        print('tick')
        curr_volume_stats, prev_volume_stats = await d.volume_recorder.get_previous_and_current_sum(DAY)
        print('curr_volume_stats', curr_volume_stats)
        print('prev_volume_stats', prev_volume_stats)

    receiver = Receiver(d, callback=cb)
    volume_filler.add_subscriber(receiver)

    await asyncio.gather(
        fetcher_tx.run(),
        d.block_scanner.run(),
        d.pool_fetcher.run(),
    )


async def tool_get_total_volume_and_tx_count(app: LpAppFramework):
    d = app.deps

    t = now_ts()
    total_volume = await d.volume_recorder.get_sum(t - 365 * DAY, t)
    print(total_volume)

    txs = await d.tx_count_recorder.get_stats(365)
    print(txs)


async def main():
    app = LpAppFramework(log_level=logging.INFO)
    async with app:
        await continuous_volume_recording(app)
        # await demo_show_price_graph(app)
        # await debug_post_price_graph_to_discord(app)
        # await tool_get_total_volume_and_tx_count(app)


if __name__ == '__main__':
    asyncio.run(main())
