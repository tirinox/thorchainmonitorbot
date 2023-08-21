import asyncio
import logging

from services.dialog.picture.price_picture import price_graph_from_db
from services.jobs.fetch.gecko_price import fill_rune_price_from_gecko
from services.jobs.fetch.tx import TxFetcher
from services.jobs.volume_filler import VolumeFillerUpdater
from services.jobs.volume_recorder import VolumeRecorder
from services.lib.draw_utils import save_image_and_show
from services.notify.types.price_notify import PriceNotifier
from tools.debug.dbg_discord import debug_prepare_discord_bot
from tools.debug.dbg_supply_graph import debug_get_rune_market_data
from tools.lib.lp_common import LpAppFramework, Receiver


async def continuous_volume_recording(lp_app):
    fetcher_tx = TxFetcher(lp_app.deps)

    volume_filler = VolumeFillerUpdater(lp_app.deps)
    fetcher_tx.add_subscriber(volume_filler)

    volume_recorder = VolumeRecorder(lp_app.deps)
    volume_filler.add_subscriber(volume_recorder)

    async def on_data(sender: VolumeRecorder, data):
        last_data = await sender.get_data_instant()
        print(last_data)
        # print(await sender.get_data_range_ago_n(HOUR * 3, 10))

    volume_recorder.add_subscriber(Receiver(callback=on_data))

    await fetcher_tx.run()


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
        await demo_show_price_graph(app)
        # await debug_post_price_graph_to_discord(app)


if __name__ == '__main__':
    asyncio.run(main())
