import asyncio
import logging
import os

from services.dialog.picture.price_picture import price_graph_from_db
from services.jobs.fetch.gecko_price import fill_rune_price_from_gecko
from services.jobs.fetch.tx import TxFetcher
from services.jobs.volume_filler import VolumeFillerUpdater
from services.jobs.volume_recorder import VolumeRecorder
from services.lib.date_utils import HOUR
from services.lib.draw_utils import img_to_bio
from tools.lib.lp_common import LpAppFramework, Receiver


async def continuous_volume_recording(lp_app):
    fetcher_tx = TxFetcher(lp_app.deps)

    volume_filler = VolumeFillerUpdater(lp_app.deps)
    fetcher_tx.subscribe(volume_filler)

    volume_recorder = VolumeRecorder(lp_app.deps)
    volume_filler.subscribe(volume_recorder)

    async def on_data(sender: VolumeRecorder, data):
        print(await sender.get_data_range_ago_n(HOUR * 3, 10))

    volume_recorder.subscribe(Receiver(callback=on_data))

    await fetcher_tx.run()


async def show_price_graph(lp_app):
    await fill_rune_price_from_gecko(lp_app.deps.db, include_fake_det=True)
    loc = lp_app.deps.loc_man.default
    graph, graph_name = await price_graph_from_db(lp_app.deps, loc)
    with open('../temp/price_gr.png', 'wb') as f:
        f.write(img_to_bio(graph, graph_name).getbuffer())
        os.system(f'open "../temp/price_gr.png"')


async def main():
    lp_app = LpAppFramework(log_level=logging.INFO)
    async with lp_app(brief=True):
        # await continuous_volume_recording(lp_app)
        await show_price_graph(lp_app)

if __name__ == '__main__':
    asyncio.run(main())
