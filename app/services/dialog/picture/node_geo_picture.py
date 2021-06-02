import logging
import math
import time
from collections import Counter
from typing import List, Tuple

from PIL import ImageDraw, Image

from services.dialog.picture.lp_picture import Resources
from services.lib.draw_utils import generate_gradient, draw_arc_aa, get_palette_color_by_index
from services.lib.geo_ip import GeoIPManager
from services.lib.plot_graph import PlotGraph
from services.lib.utils import async_wrap

NODE_GEO_PIC_WIDTH, NODE_GEO_PIC_HEIGHT = 600, 800


def radial_pos_int(cx, cy, r, angle_deg):
    a = angle_deg / 180 * math.pi
    x = cx + r * math.cos(a)
    y = cy + r * math.sin(a)
    return int(x), int(y)


def make_donut_chart(elements: List[Tuple[str, int]], width=400, margin=4, line_width=40, gap=1, label_r=200,
                     total_color='white'):
    image = Image.new('RGBA', (width, width), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

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

    font = Resources().font_small

    gap *= 0.5
    cx = cy = width // 2

    current = 0
    deg_per_one = 360 / total_count
    for i, (label, value) in enumerate(elements):
        arc_len = deg_per_one * value

        color = get_palette_color_by_index(i)
        arc_start = current + gap
        arc_end = current + arc_len - gap
        if arc_start < arc_end:
            draw_arc_aa(image, ellipsis_bbox,
                        arc_start, arc_end,
                        line_width, color)

        draw.text(radial_pos_int(cx, cy, label_r, current + arc_len / 2),
                  str(value),
                  font=font, fill=color, anchor='mm')

        current += arc_len

    if total_color:
        draw.text((cx, cy), str(total_count), fill=total_color, font=Resources().font_big, anchor='mm')

    return image


def most_common_and_other(values: list, max_categories, other_str='Others'):
    provider_counter = Counter(values)
    total = sum(provider_counter.values())
    elements = provider_counter.most_common(max_categories)
    total_most_common = sum(item[1] for item in elements)
    others_sum = total - total_most_common
    elements.append((other_str, others_sum))
    return elements


@async_wrap
def node_geo_pic(ip_infos: List[dict], max_categories=3):
    image = generate_gradient(PlotGraph.GRADIENT_TOP_COLOR, PlotGraph.GRADIENT_BOTTOM_COLOR, NODE_GEO_PIC_WIDTH,
                              NODE_GEO_PIC_HEIGHT)

    providers = {}
    for info in ip_infos:
        if info:
            ip = info['ip']
            providers[ip] = GeoIPManager.get_general_provider(info)

    elements = most_common_and_other(list(providers.values()), max_categories, 'Others')
    print(elements)

    t0 = time.monotonic()
    donut = make_donut_chart(elements, width=400, margin=64, line_width=40, gap=2, label_r=140)
    t1 = time.monotonic()
    logging.info(f'node_geo_pic: donat chart time = {(t1 - t0):.3f} sec')
    image.paste(donut, (100, 100), mask=donut)

    # draw_arc_aa(image, (10, 10, 200, 120), 20, 120, width=20, outline='white')

    return image
