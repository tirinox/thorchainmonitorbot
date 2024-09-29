from comm.localization.manager import BaseLocalization
from comm.picture.common import PictureAndName
from jobs.volume_recorder import VolumeRecorder
from lib.constants import RUNE_SYMBOL_DET, RUNE_SYMBOL_POOL, RUNE_SYMBOL_CEX
from lib.date_utils import DAY, today_str
from lib.depcont import DepContainer
from lib.plot_graph import PlotGraphLines
from lib.utils import async_wrap, pluck_from_series
from models.time_series import PriceTimeSeries
from models.vol_n import TxMetricType

PRICE_GRAPH_WIDTH = 1024
PRICE_GRAPH_HEIGHT = 768

LINE_COLOR_POOL_PRICE = '#FFD573'
LINE_COLOR_CEX_PRICE = '#61B7CF'
LINE_COLOR_DET_PRICE = '#FF8673'

BAR_COLOR_SWAP = '#0b735b'
BAR_COLOR_SWAP_SYNTH = '#118f89'
BAR_COLOR_ADD = '#04cf4e'
BAR_COLOR_WITHDRAW = '#cf0448'

VOLUME_N_POINTS = 58


@async_wrap
def price_graph(pool_price_df, det_price_df, cex_prices_df, volumes, loc: BaseLocalization, time_scale_mode='date'):
    graph = PlotGraphLines(PRICE_GRAPH_WIDTH, PRICE_GRAPH_HEIGHT)
    graph.show_min_max = True
    graph.left = 80
    graph.legend_x = 95
    graph.bottom = 100

    graph.add_series(cex_prices_df, LINE_COLOR_CEX_PRICE)
    graph.add_series(pool_price_df, LINE_COLOR_POOL_PRICE)  # pool price's line is on top of CEX line
    graph.add_series(det_price_df, LINE_COLOR_DET_PRICE)

    graph.legend_x = 20

    graph.add_legend(LINE_COLOR_POOL_PRICE, loc.PRICE_GRAPH_LEGEND_ACTUAL_PRICE)
    graph.add_legend(LINE_COLOR_CEX_PRICE, loc.PRICE_GRAPH_LEGEND_CEX_PRICE)
    graph.add_legend(LINE_COLOR_DET_PRICE, loc.PRICE_GRAPH_LEGEND_DET_PRICE)

    graph.bar_height_limit = 200

    # In the series, swaps = L1 swaps + synths swaps. So this is the tall bar behind "only synth" swaps
    graph.add_series_bars(pluck_from_series(volumes, TxMetricType.SWAP), BAR_COLOR_SWAP, 8)
    graph.add_series_bars(pluck_from_series(volumes, TxMetricType.SWAP_SYNTH), BAR_COLOR_SWAP_SYNTH, 8)
    graph.add_series_bars(pluck_from_series(volumes, TxMetricType.ADD_LIQUIDITY), BAR_COLOR_ADD, 2, -3)
    graph.add_series_bars(pluck_from_series(volumes, TxMetricType.WITHDRAW_LIQUIDITY), BAR_COLOR_WITHDRAW, 2, 3)

    graph.add_legend(BAR_COLOR_SWAP, loc.PRICE_GRAPH_VOLUME_SWAP_NORMAL)
    graph.add_legend(BAR_COLOR_SWAP_SYNTH, loc.PRICE_GRAPH_VOLUME_SWAP_SYNTH)
    graph.add_legend(BAR_COLOR_ADD, loc.PRICE_GRAPH_VOLUME_SWAP_ADD)
    graph.add_legend(BAR_COLOR_WITHDRAW, loc.PRICE_GRAPH_VOLUME_SWAP_WITHDRAW)

    """
    Volume bar looks like this:
     ___
    |___| L1 swap
    |   | Synth swap
    |A  | A = Add liq.
    |A  |
    |A W| W = Withdraw liq.
    |A W|
    |A W|
    """

    graph.update_bounds()
    graph.min_y = 0.0
    graph.max_y *= 1.1
    graph.n_ticks_x = 8
    graph.n_ticks_y = 8
    graph.grid_lines = True
    graph.line_width = 2

    graph.add_title(loc.PRICE_GRAPH_TITLE)

    graph.y_formatter = lambda y: f'${y:.3f}'
    graph.x_formatter = graph.date_formatter if time_scale_mode == 'date' else graph.time_formatter

    return graph.finalize()


async def price_graph_from_db(deps: DepContainer, loc: BaseLocalization, period=DAY) -> PictureAndName:
    series = PriceTimeSeries(RUNE_SYMBOL_POOL, deps.db)
    det_series = PriceTimeSeries(RUNE_SYMBOL_DET, deps.db)
    cex_price_series = PriceTimeSeries(RUNE_SYMBOL_CEX, deps.db)
    volume_recorder = VolumeRecorder(deps)

    max_points = 10_000
    if period >= 7 * DAY:
        max_points = 60_000

    prices = await series.get_last_values(period, with_ts=True, max_points=max_points)
    det_prices = await det_series.get_last_values(period, with_ts=True, max_points=max_points)
    cex_prices = await cex_price_series.get_last_values(period, with_ts=True, max_points=max_points)
    volumes = await volume_recorder.get_data_range_ago_n(period, n=VOLUME_N_POINTS)

    time_scale_mode = 'time' if period <= DAY else 'date'

    img = await price_graph(prices, det_prices, cex_prices, volumes, loc, time_scale_mode=time_scale_mode)
    return img, f'price-{today_str()}.jpg'
