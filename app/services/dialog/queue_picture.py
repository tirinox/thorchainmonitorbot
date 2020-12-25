import pandas as pd

from localization import BaseLocalization
from services.lib.datetime import series_to_pandas, DAY
from services.lib.depcont import DepContainer
from services.lib.plot_graph import PlotBarGraph
from services.lib.utils import async_wrap
from services.models.time_series import TimeSeries
from services.notify.types.queue_notify import QueueNotifier


RESAMPLE_TIME = '10min'


async def queue_graph(d: DepContainer, loc: BaseLocalization):
    ts = TimeSeries(QueueNotifier.QUEUE_TIME_SERIES, d.db)
    points = await ts.select(*ts.range_from_ago_to_now(DAY, tolerance_sec=10), count=10000)
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
    gr.add_title(loc.TEXT_QUEUE_PLOT_TITLE)
    return gr.finalize()
