import asyncio
import math

from comm.dialog.picture.block_height_picture import PRICE_GRAPH_WIDTH, PRICE_GRAPH_HEIGHT, LINE_COLOR_ACTUAL
from lib.money import DepthCurve, short_dollar
from lib.plot_graph import PlotGraphLines
from lib.utils import async_wrap
from tools.lib.lp_common import LpAppFramework


@async_wrap
def curve_chart(pts):
    # pts = [
    #     [1, 10],
    #     [100, 20],
    #     [1000, 35],
    #     [10000, 25],
    #     [100000, 13]
    # ]

    graph = PlotGraphLines(PRICE_GRAPH_WIDTH, PRICE_GRAPH_HEIGHT)
    graph.show_min_max = True
    graph.left = 80
    graph.legend_x = 95
    graph.bottom = 100
    graph.add_series([
        [(math.log10(d) if d else 0.0), (math.log10(p))] for d, p in pts
    ], LINE_COLOR_ACTUAL)

    graph.update_bounds()
    graph.min_y = 0.0
    graph.max_y *= 1.1
    graph.n_ticks_x = 10
    graph.n_ticks_y = 20
    graph.grid_lines = True
    graph.line_width = 3

    graph.add_title('Curve')

    log_dollar = lambda y: short_dollar(10 ** y)
    graph.y_formatter = log_dollar
    graph.x_formatter = log_dollar

    return graph.finalize()


async def run():
    app = LpAppFramework()
    async with app(brief=True):
        curve = DepthCurve.default()

        mult = 0.5
        max_d = 100e6
        f = 1.3

        depths = [10000]
        while (last := depths[-1]) < max_d:
            depths.append(last * f)

        pts = [
            (d, curve.evaluate(d) * d * mult) for d in depths
        ]
        chart = await curve_chart(pts)
        chart.show()


if __name__ == '__main__':
    asyncio.run(run())
