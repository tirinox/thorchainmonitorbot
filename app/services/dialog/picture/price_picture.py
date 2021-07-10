from localization import BaseLocalization
from services.lib.constants import RUNE_SYMBOL_DET, RUNE_SYMBOL_POOL, RUNE_SYMBOL_CEX
from services.lib.date_utils import DAY, today_str
from services.lib.db import DB
from services.lib.draw_utils import img_to_bio
from services.lib.plot_graph import PlotGraphLines
from services.lib.utils import async_wrap
from services.models.time_series import PriceTimeSeries

PRICE_GRAPH_WIDTH = 640
PRICE_GRAPH_HEIGHT = 480

LINE_COLOR_POOL_PRICE = '#FFD573'
LINE_COLOR_CEX_PRICE = '#61B7CF'
LINE_COLOR_DET_PRICE = '#FF8673'


@async_wrap
def price_graph(pool_price_df, det_price_df, cex_prices_df, loc: BaseLocalization, time_scale_mode='date'):
    graph = PlotGraphLines(PRICE_GRAPH_WIDTH, PRICE_GRAPH_HEIGHT)
    graph.left = 80
    graph.legend_x = 95
    graph.bottom = 100
    graph.add_series(pool_price_df, LINE_COLOR_POOL_PRICE)
    graph.add_series(cex_prices_df, LINE_COLOR_CEX_PRICE)
    graph.add_series(det_price_df, LINE_COLOR_DET_PRICE)
    graph.update_bounds()
    graph.min_y = 0.0
    graph.max_y *= 1.1
    graph.n_ticks_x = 8
    graph.n_ticks_y = 8
    graph.grid_lines = True

    graph.add_title(loc.PRICE_GRAPH_TITLE)

    graph.add_legend(LINE_COLOR_POOL_PRICE, loc.PRICE_GRAPH_LEGEND_ACTUAL_PRICE)
    graph.add_legend(LINE_COLOR_CEX_PRICE, loc.PRICE_GRAPH_LEGEND_CEX_PRICE)
    graph.add_legend(LINE_COLOR_DET_PRICE, loc.PRICE_GRAPH_LEGEND_DET_PRICE)

    graph.y_formatter = lambda y: f'${y:.3}'
    graph.x_formatter = graph.date_formatter if time_scale_mode == 'date' else graph.time_formatter

    return graph.finalize()


async def price_graph_from_db(db: DB, loc: BaseLocalization, period=DAY):
    series = PriceTimeSeries(RUNE_SYMBOL_POOL, db)
    det_series = PriceTimeSeries(RUNE_SYMBOL_DET, db)
    cex_price_series = PriceTimeSeries(RUNE_SYMBOL_CEX, db)

    prices = await series.get_last_values(period, with_ts=True)
    det_prices = await det_series.get_last_values(period, with_ts=True)
    cex_prices = await cex_price_series.get_last_values(period, with_ts=True)

    time_scale_mode = 'time' if period <= DAY else 'date'

    img = await price_graph(prices, det_prices, cex_prices, loc, time_scale_mode=time_scale_mode)
    return img_to_bio(img, f'price-{today_str()}.jpg')
