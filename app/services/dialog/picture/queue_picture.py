import pandas as pd

from localization.manager import BaseLocalization
from services.dialog.picture.common import PictureAndName
from services.lib.date_utils import ts_event_points_to_pandas, DAY, today_str
from services.lib.depcont import DepContainer
from services.lib.draw_utils import CATEGORICAL_PALETTE
from services.lib.plot_graph import PlotBarGraph
from services.lib.utils import async_wrap
from services.models.time_series import TimeSeries

QUEUE_TIME_SERIES = 'thor_queue'
RESAMPLE_TIME = '10min'

MIN_POINTS = 4


async def queue_graph(d: DepContainer, loc: BaseLocalization, duration=DAY) -> PictureAndName:
    ts = TimeSeries(QUEUE_TIME_SERIES, d.db)
    points = await ts.select(*ts.range_from_ago_to_now(duration, tolerance_sec=10), count=10000)
    if not points or len(points) < MIN_POINTS:
        return None, ''
    return await queue_graph_sync(points, loc)


@async_wrap
def queue_graph_sync(event_points, loc: BaseLocalization):
    df = ts_event_points_to_pandas(event_points, shift_time=False)
    df["t"] = pd.to_datetime(df["t"], unit='s')
    df = df.resample(RESAMPLE_TIME, on='t').sum()

    gr = PlotBarGraph()
    gr.plot_bars(df, 'outbound', gr.PLOT_COLOR)
    gr.plot_bars(df, 'swap', gr.PLOT_COLOR_2)
    gr.plot_bars(df, 'internal', CATEGORICAL_PALETTE[0])
    gr.update_bounds_y()
    gr.max_y = max(gr.max_y, 20)
    gr.add_title(loc.TEXT_QUEUE_PLOT_TITLE)
    today = today_str()
    return gr.finalize(), f'thorchain_queue_{today}.png'
