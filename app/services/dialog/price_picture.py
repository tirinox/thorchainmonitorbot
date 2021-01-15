from localization import BaseLocalization
from services.lib.datetime import DAY
from services.lib.db import DB
from services.lib.plot_graph import PlotGraphLines
from services.lib.utils import async_wrap
from services.models.time_series import PriceTimeSeries, RUNE_SYMBOL, RUNE_SYMBOL_DET

PRICE_GRAPH_WIDTH = 640
PRICE_GRAPH_HEIGHT = 480

LINE_COLOR_REAL_PRICE = '#ffa600'
LINE_COLOR_DET_PRICE = '#ff6361'


@async_wrap
def price_graph(price_df, det_price_df, loc: BaseLocalization):
    graph = PlotGraphLines(PRICE_GRAPH_WIDTH, PRICE_GRAPH_HEIGHT)
    graph.left = 80
    graph.legend_x = 195
    graph.bottom = 100
    graph.add_series(price_df, LINE_COLOR_REAL_PRICE)
    graph.add_series(det_price_df, LINE_COLOR_DET_PRICE)
    graph.update_bounds()
    graph.min_y = 0.0
    graph.max_y *= 1.1
    graph.n_ticks_x = 8
    graph.n_ticks_y = 8

    graph.add_title(loc.PRICE_GRAPH_TITLE)

    graph.add_legend(LINE_COLOR_DET_PRICE, loc.PRICE_GRAPH_LEGEND_DET_PRICE)
    graph.add_legend(LINE_COLOR_REAL_PRICE, loc.PRICE_GRAPH_LEGEND_ACTUAL_PRICE)

    graph.y_formatter = lambda y: f'${y:.3}'
    graph.x_formatter = graph.date_formatter

    return graph.finalize()


async def price_graph_from_db(db: DB, loc: BaseLocalization):
    series = PriceTimeSeries(RUNE_SYMBOL, db)
    det_series = PriceTimeSeries(RUNE_SYMBOL_DET, db)

    prices = await series.get_last_values(DAY, with_ts=True)
    det_prices = await det_series.get_last_values(DAY, with_ts=True)

    img = await price_graph(prices, det_prices, loc)
    return img
