import logging
import math
import time
from typing import List, Tuple

from PIL import ImageDraw, Image, ImageFont

from localization.eng_base import BaseLocalization
from services.lib.draw_utils import draw_arc_aa, get_palette_color_by_index, LIGHT_TEXT_COLOR, \
    hls_transform_hex, default_gradient
from services.lib.texts import grouper
from services.lib.utils import async_wrap, Singleton, most_common_and_other
from services.models.node_info import NetworkNodeIpInfo

NODE_GEO_PIC_WIDTH, NODE_GEO_PIC_HEIGHT = 800, 720


async def node_geo_pic(info: NetworkNodeIpInfo, loc: BaseLocalization, max_categories=5):
    return await node_geo_pic_sync(info, loc, max_categories)


# ----------------------------------------------------------------------------------------------------------------------

class Resources(metaclass=Singleton):
    BASE = './data'
    BG_IMG = f'{BASE}/lp_bg.png'

    FONT_BOLD = f'{BASE}/my.ttf'

    def __init__(self) -> None:
        self.font_large = ImageFont.truetype(self.FONT_BOLD, 68)
        self.font_head = ImageFont.truetype(self.FONT_BOLD, 48)
        self.font_subtitle = ImageFont.truetype(self.FONT_BOLD, 34)
        self.font_small = ImageFont.truetype(self.FONT_BOLD, 22)
        self.font_norm = ImageFont.truetype(self.FONT_BOLD, 28)


def radial_pos_int(cx, cy, r, angle_deg):
    a = angle_deg / 180 * math.pi
    x = cx + r * math.cos(a)
    y = cy + r * math.sin(a)
    return int(x), int(y)


SegmentDesc = Tuple[str, int, bool]  # Name, Value, isEmpty?


def get_disabled_palette_color_by_index(i):
    def disable_color_hls(h, l, s):
        l *= 0.9
        s *= 0.5
        return h, l, s

    return hls_transform_hex(get_palette_color_by_index(i), disable_color_hls)


def make_donut_chart(elements: List[Tuple[str, int]],
                     width=400, margin=4, line_width=40, gap=1, label_r=0,
                     title_color=LIGHT_TEXT_COLOR,
                     font_middle=None,
                     font_abs_count=None,
                     font_percent=None,
                     palette=None):
    # bg_color = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255), 0)
    bg_color = (0, 0, 0, 0)
    image = Image.new('RGBA', (width, width), bg_color)
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

    gap *= 0.5
    cx = cy = width // 2

    current = 0
    deg_per_one = 360 / total_count
    for i, (label, value) in enumerate(elements):
        arc_len = deg_per_one * value

        color = palette(i) if palette else get_palette_color_by_index(i)

        arc_start = current + gap
        arc_end = current + arc_len - gap
        if arc_start < arc_end:
            draw_arc_aa(image, ellipsis_bbox,
                        arc_start, arc_end,
                        line_width, color)

        if font_abs_count:
            r = label_r if label_r else width // 2 - margin + line_width * 0.4
            x, y = radial_pos_int(cx, cy, r, current + arc_len / 2)
            draw.text((x, y),
                      str(value),
                      font=font_abs_count, fill=color, anchor='mm')

        if font_percent:
            x, y = radial_pos_int(cx, cy, width // 2 - margin - line_width * 0.6, current + arc_len / 2)
            draw.text((x, y), f"{int(value / total_count * 100.)}%", color, font=font_percent, anchor='mm')

        current += arc_len

    if title_color and font_middle:
        title = str(total_count)
        draw.text((cx, cy), title, fill=title_color, font=font_middle, anchor='mm')

    return image


def geo_legend(draw: ImageDraw, elements: List[str], xy, font, width=400, sq_size=12, y_step=20, items_in_row=3):
    x, y = xy

    line_groups = list(grouper(items_in_row, elements))
    legend_dx = width / items_in_row if items_in_row >= 2 else 0
    counter = 0

    for line in line_groups:
        current_x = x
        for label in line:
            color = get_palette_color_by_index(counter)
            draw.rectangle((
                (current_x, y),
                (current_x + sq_size, y + sq_size)
            ), fill=color)

            draw.text((current_x + sq_size + 10, y + 2), label, LIGHT_TEXT_COLOR, font=font, anchor='lt')

            current_x += legend_dx
            counter += 1
        y += y_step


@async_wrap
def node_geo_pic_sync(info: NetworkNodeIpInfo, loc: BaseLocalization, max_categories=3):
    w, h = NODE_GEO_PIC_WIDTH, NODE_GEO_PIC_HEIGHT
    image = default_gradient(w, h)

    r = Resources()
    draw = ImageDraw.Draw(image)

    cx = image.width // 2

    # 1. HEADER
    draw.text((cx, 30),
              loc.TEXT_PIC_NODE_DIVERSITY,
              fill=LIGHT_TEXT_COLOR,
              font=r.font_head, anchor='mt')

    draw.text((cx, 80),
              loc.TEXT_PIC_NODE_DIVERSITY_SUBTITLE,
              fill=LIGHT_TEXT_COLOR,
              font=r.font_small, anchor='mt')

    h_line_y = 110
    draw.line((0, h_line_y, w, h_line_y), '#468', 2)

    # 2. CHART
    t0 = time.perf_counter()

    def one_donut(node_list, xy, big, title, palette):
        providers = info.get_providers(node_list)
        providers = [(loc.TEXT_PIC_UNKNOWN if p == NetworkNodeIpInfo.UNKNOWN_PROVIDER else p)
                     for p in providers]
        elements = most_common_and_other(providers,
                                         max_categories,
                                         loc.TEXT_PIC_OTHERS)
        donut_w = 360 if big else 210
        donut = make_donut_chart(elements,
                                 width=donut_w,
                                 margin=40 if big else 34,
                                 line_width=100 if big else 72,
                                 gap=2 if big else 1,
                                 label_r=164 if big else 90,
                                 font_middle=r.font_large if big else r.font_head,
                                 font_percent=None,
                                 font_abs_count=r.font_norm,
                                 palette=palette)
        image.paste(donut, xy, mask=donut)

        x, y = xy
        ty = y - 10
        draw.text((x + donut_w // 2, ty), title, fill=LIGHT_TEXT_COLOR,
                  font=r.font_subtitle if big else r.font_norm,
                  anchor='mb')

        return elements

    elements_all = \
        one_donut(info.node_info_list, (w // 2 - 180, 160), True,
                  loc.TEXT_PIC_ALL_NODES,
                  palette=None)

    sdhw = 210 // 2
    sdy = 230
    sdd = 280

    one_donut(info.active_nodes, (w // 2 - sdhw - sdd, sdy), False,
              loc.TEXT_PIC_ACTIVE_NODES,
              palette=None)

    one_donut(info.not_active_nodes, (w // 2 - sdhw + sdd, sdy), False,
              loc.TEXT_PIC_STANDBY_NODES,
              palette=get_disabled_palette_color_by_index)

    t1 = time.perf_counter()
    logging.info(f'node_geo_pic: donat chart time = {(t1 - t0):.3f} sec')

    # 3. LEGEND
    only_providers = [e[0] for e in elements_all]

    lmar = 100
    geo_legend(draw, only_providers, (lmar, 560), r.font_norm, w - lmar * 2,
               sq_size=24, y_step=36, items_in_row=2)

    return image
