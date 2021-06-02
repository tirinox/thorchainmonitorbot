import time
from collections import Counter
from typing import List, Tuple

from PIL import ImageDraw, Image

from services.lib.draw_utils import generate_gradient, draw_arc_aa, get_palette_color_by_index
from services.lib.geo_ip import GeoIPManager
from services.lib.plot_graph import PlotGraph
from services.lib.utils import async_wrap

NODE_GEO_PIC_WIDTH, NODE_GEO_PIC_HEIGHT = 600, 800


def make_donut_chart(elements: List[Tuple[str, int]], width=400, margin=4, line_width=40):
    image = Image.new('RGBA', (width, width), (0, 0, 0, 0))

    elements = [item for item in elements if item[1] > 0]  # filter out bad values
    total_count = sum(item[1] for item in elements)
    if not total_count:
        return image  # nothing to plot!

    half_width = line_width // 2
    ellipsis_bbox = [
        margin + half_width,
        margin + half_width,
        width - margin - half_width,
        width - margin - half_width
    ]

    start = 0
    deg_per_one = 360 / total_count
    for i, (label, value) in enumerate(elements):
        arc_len = deg_per_one * value

        color = get_palette_color_by_index(i)
        draw_arc_aa(image, ellipsis_bbox, start, start + arc_len, line_width, color)

        start += arc_len

    return image


@async_wrap
def node_geo_pic(ip_infos: List[dict], max_categories=4):
    image = generate_gradient(PlotGraph.GRADIENT_TOP_COLOR, PlotGraph.GRADIENT_BOTTOM_COLOR, NODE_GEO_PIC_WIDTH,
                              NODE_GEO_PIC_HEIGHT)
    draw = ImageDraw.Draw(image)

    providers = {}
    for info in ip_infos:
        if info:
            ip = info['ip']
            providers[ip] = GeoIPManager.get_general_provider(info)

    provider_counter = Counter(providers.values())
    elements = provider_counter.most_common(max_categories)

    t0 = time.monotonic()
    donut = make_donut_chart(elements)
    t1 = time.monotonic()
    print(f'dt = {(t1 - t0):.3f} sec')
    image.paste(donut, (100, 100), mask=donut)

    # draw_arc_aa(image, (10, 10, 200, 120), 20, 120, width=20, outline='white')

    return image
