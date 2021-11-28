from localization import BaseLocalization
from services.lib.date_utils import today_str
from services.lib.draw_utils import img_to_bio
from services.lib.plot_graph import PlotGraphLines
from services.lib.utils import async_wrap

PRICE_GRAPH_WIDTH = 640
PRICE_GRAPH_HEIGHT = 480

LINE_COLOR_ACTUAL = '#FFD573'
LINE_COLOR_EXPECTED = '#61B7CF'


async def block_speed_chart(last_points, loc: BaseLocalization, normal_bpm=10, time_scale_mode='date'):
    return await block_speed_chart_sync(last_points, loc, normal_bpm, time_scale_mode)


@async_wrap
def block_speed_chart_sync(last_points, loc: BaseLocalization, normal_bpm=10, time_scale_mode='date'):
    graph = PlotGraphLines(PRICE_GRAPH_WIDTH, PRICE_GRAPH_HEIGHT)
    graph.show_min_max = True
    graph.left = 80
    graph.legend_x = 95
    graph.bottom = 100
    graph.add_series(last_points, LINE_COLOR_ACTUAL)

    if len(last_points) >= 2:
        graph.add_series([
            (last_points[0][0], normal_bpm),
            (last_points[-1][0], normal_bpm)
        ], LINE_COLOR_EXPECTED)

    graph.update_bounds()
    graph.min_y = 0.0
    graph.max_y *= 1.1
    graph.n_ticks_x = 8
    graph.n_ticks_y = 8
    graph.grid_lines = True
    graph.line_width = 3

    graph.add_title(loc.TEXT_BLOCK_HEIGHT_CHART_TITLE)

    graph.add_legend(LINE_COLOR_ACTUAL, loc.TEXT_BLOCK_HEIGHT_LEGEND_ACTUAL)
    graph.add_legend(LINE_COLOR_EXPECTED, loc.TEXT_BLOCK_HEIGHT_LEGEND_EXPECTED)

    graph.y_formatter = lambda y: f'{y:.1f}'
    graph.x_formatter = graph.date_formatter if time_scale_mode == 'date' else graph.time_formatter

    pic = graph.finalize()
    return img_to_bio(pic, f'block-gen-{today_str()}.jpg')
