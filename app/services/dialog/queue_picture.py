import pandas as pd

from localization import BaseLocalization
from services.lib.datetime import series_to_pandas, DAY
from services.lib.depcont import DepContainer
from services.lib.plot_graph import PlotBarGraph, img_to_bio
from services.lib.utils import async_wrap
from services.models.time_series import TimeSeries

QUEUE_TIME_SERIES = 'thor_queue'
RESAMPLE_TIME = '10min'


async def queue_graph(d: DepContainer, loc: BaseLocalization, duration=DAY):
    ts = TimeSeries(QUEUE_TIME_SERIES, d.db)
    points = await ts.select(*ts.range_from_ago_to_now(duration, tolerance_sec=10), count=10000)
    if not points:
        return None
    return await queue_graph_sync(points, loc)


@async_wrap
def queue_graph_sync(points, loc: BaseLocalization):
    df = series_to_pandas(points, shift_time=False)
    df["t"] = pd.to_datetime(df["t"], unit='s')
    df = df.resample(RESAMPLE_TIME, on='t').sum()

    gr = PlotBarGraph()
    gr.plot_bars(df, 'outbound_queue', gr.PLOT_COLOR)
    gr.plot_bars(df, 'swap_queue', gr.PLOT_COLOR_2)
    gr.update_bounds_y()
    gr.max_y = max(gr.max_y, 20)
    gr.add_title(loc.TEXT_QUEUE_PLOT_TITLE)
    return img_to_bio(gr.finalize(), 'thorchain_queue.png')
