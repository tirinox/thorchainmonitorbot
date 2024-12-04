from comm.localization.eng_base import BaseLocalization
from lib.date_utils import today_str
from lib.draw_utils import TC_YGGDRASIL_GREEN
from lib.money import short_rune
from lib.plot_graph import PlotBarGraph
from lib.utils import async_wrap

RESAMPLE_TIME = '4h'


@async_wrap
def rune_burn_graph(df, loc: BaseLocalization, days=7):
    gr = PlotBarGraph(bg='black')
    gr.plot_bars(df, 'max_supply_delta', TC_YGGDRASIL_GREEN)
    gr.update_bounds_y()

    gr.add_title(loc.RUNE_BURN_GRAPH_TITLE)
    gr.y_formatter = lambda y: short_rune(y)
    gr.x_formatter = gr.date_formatter
    gr.n_ticks_y = 8
    gr.n_ticks_x = round(days)
    gr.margin = 4
    gr.min_y = min(gr.min_y, 0)
    today = today_str()
    return gr.finalize(), f'thorchain_rune_burn_{today}.png'
