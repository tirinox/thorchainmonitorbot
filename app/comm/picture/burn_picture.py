import pandas as pd

from comm.localization.eng_base import BaseLocalization
from lib.constants import thor_to_float
from lib.date_utils import ts_event_points_to_pandas, today_str
from lib.draw_utils import CATEGORICAL_PALETTE
from lib.plot_graph import PlotBarGraph
from lib.utils import async_wrap

RESAMPLE_TIME = '12h'


@async_wrap
def rune_burn_graph(event_points, loc: BaseLocalization, resample_time=RESAMPLE_TIME):
    df = ts_event_points_to_pandas(event_points, shift_time=False)
    df.describe()
    df["t"] = pd.to_datetime(df["t"], unit='s')
    df['max_supply'] = df['max_supply'].apply(thor_to_float)
    df['max_supply_delta'] = -df['max_supply'].diff().dropna()

    df = df.resample(resample_time, on='t').mean()

    # Show only the 't' and 'max_supply_delta' columns
    # df_deltas = df[['t', 'max_supply_delta']]

    gr = PlotBarGraph()
    gr.plot_bars(df, 'max_supply_delta', CATEGORICAL_PALETTE[0])
    gr.update_bounds_y()
    # gr.max_y = max(gr.max_y, 20)
    gr.add_title(loc.RUNE_BURN_GRAPH_TITLE)
    gr.y_formatter = lambda y: f'{y:.2f}'
    gr.x_formatter = gr.date_formatter
    gr.min_y = min(gr.min_y, 0)
    today = today_str()
    return gr.finalize(), f'thorchain_rune_burn_{today}.png'
