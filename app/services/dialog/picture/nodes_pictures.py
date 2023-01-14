import math
import random
from collections import defaultdict
from typing import List

from PIL import Image, ImageDraw

from localization.eng_base import BaseLocalization
from services.dialog.picture.resources import Resources
from services.lib.date_utils import DAY, now_ts, today_str
from services.lib.draw_utils import default_background, CacheGrid, TC_YGGDRASIL_GREEN, \
    make_donut_chart, TC_NIGHT_BLACK, TC_PALETTE, TC_WHITE, TC_LIGHTNING_BLUE, get_palette_color_by_index
from services.lib.money import clamp, short_rune, format_percent
from services.lib.plot_graph import plot_legend, PlotGraphLines
from services.lib.texts import bracketify
from services.lib.utils import async_wrap, Singleton, most_common_and_other, linear_transform
from services.models.node_info import NetworkNodeIpInfo, NodeStatsItem


class ResourcesNodePic(metaclass=Singleton):
    BASE = Resources.BASE
    WORLD_FILE = f'{BASE}/earth-bg.png'
    LOGO_FILE = f'{BASE}/tc_logo.png'
    CIRCLE_FILE = f'{BASE}/circle_new.png'
    CIRCLE_DIM_FILE = f'{BASE}/circle-dim.png'

    def __init__(self) -> None:
        r = Resources()

        f = self.fonts = r.fonts
        self.font_xs = f.get_font(24)
        self.font_small = f.get_font(30)
        self.font_norm = f.get_font(34)
        self.font_large = f.get_font(40)
        self.font_subtitle = f.get_font(44, f.FONT_BOLD)
        self.font_head = f.get_font(80)

        self.world_map = Image.open(self.WORLD_FILE)
        self.tc_logo = r.tc_logo
        self.circle = Image.open(self.CIRCLE_FILE)
        self.circle_dim = Image.open(self.CIRCLE_DIM_FILE)


class WorldMap:
    # todo: move this to config
    MANUAL_COORDS = {
        # City: (lat, long)
        'Karuwisi': (-5.1333, 119.4167),
    }

    def __init__(self, loc: BaseLocalization):
        self.r = ResourcesNodePic()
        self.w, self.h = self.r.world_map.size
        self.loc = loc
        self.label_color = '#ddd'

    def convert_coord_to_xy(self, long, lat):
        x = (long + 180.0) / 360.0 * self.w
        y = (90.0 - lat) / 180.0 * self.h
        return x, y

    def draw(self, data: NetworkNodeIpInfo, color_map) -> Image:
        # color_map: ip_address => (prov_name, color)
        data.sort_by_status()
        pic = self.r.world_map.copy()

        draw = ImageDraw.Draw(pic)
        randomize_factor = 0.0025
        w, h = pic.size

        node_counters = defaultdict(int)
        coord_cache = {}
        label_cache = set()

        max_point_size = 100
        min_point_size = 10
        n_unknown_nodes = 0

        name_grid = CacheGrid(20, 40)
        n_grid = CacheGrid(30, 30)

        unk_lat, unk_long = -60, -140
        name_grid.set(*self.convert_coord_to_xy(unk_long, unk_lat))

        countries = []
        labels = []
        remember_clusters = {}

        for node in data.node_info_list:
            geo = data.ip_info_dict.get(node.ip_address) or {}
            lat, long = geo.get('latitude'), geo.get('longitude')

            country = geo.get('country_name')
            city = geo.get('city')
            if country:
                countries.append(country)

            if not lat or not long:
                lat, long = self.MANUAL_COORDS.get(city, (None, None))

            if not lat or not long:
                if node.is_active:
                    lat, long = unk_lat, unk_long
                    n_unknown_nodes += 1
                else:
                    continue

            x, y = self.convert_coord_to_xy(long, lat)
            key = f'{x}-{y}'
            coord_cache[key] = (x, y)
            if key in node_counters:
                x += w * random.uniform(-randomize_factor, randomize_factor)
                y += h * random.uniform(-randomize_factor, randomize_factor)
            else:
                labels.append((x, y, city))

            node_counters[key] += 1

            point_size = ((node.bond / 1e6) ** 2) * max_point_size
            point_size = int(math.ceil(clamp(point_size, min_point_size, max_point_size)))
            point_size_half = point_size // 2

            source_image = self.r.circle if node.is_active else self.r.circle_dim

            point_image = source_image.copy()
            point_image.thumbnail((point_size, point_size), Image.ANTIALIAS)

            x, y = int(x), int(y)

            color = color_map.get(node.ip_address, (0, TC_WHITE))[1]

            point_size_half = int(point_size_half * 0.5)
            ellipse_box = (
                (x - point_size_half, y - point_size_half),
                (x + point_size_half, y + point_size_half),
            )
            draw.ellipse(ellipse_box, fill=color, outline='#000')

            name_grid.set(x, y)

            # count label:
            k = n_grid.inc(x, y)
            remember_clusters[k] = (x, y)

        label_x_shift = 30
        if n_unknown_nodes:
            x, y = self.convert_coord_to_xy(unk_long, unk_lat)
            draw.text((x + label_x_shift, y + 30),
                      f'{self.loc.TEXT_PIC_UNKNOWN_LOCATION} ({n_unknown_nodes})',
                      fill='#005566',
                      font=self.r.font_small, anchor='mt')

        # Cluster node counts
        for k, (x, y) in remember_clusters.items():
            if (n := int(n_grid[k])) > 1:
                draw.text((x, y), str(n),
                          fill=TC_WHITE,
                          font=self.r.font_xs,
                          anchor='mm',
                          stroke_fill=TC_NIGHT_BLACK,
                          stroke_width=1)

        # City names
        def plot_city(name, position, sx, sy, w, h):
            if position == 'left':
                x_start = sx - label_x_shift - w
                text_x = x_end = sx - label_x_shift
            else:
                text_x = x_start = sx + label_x_shift
                x_end = sx + label_x_shift + w

            box = (x_start, sy - h // 2), (x_end, sy + h // 2)
            if not name_grid.is_box_occupied(box):
                draw.text((text_x, sy), name,
                          fill=self.label_color,
                          font=self.r.font_xs,
                          anchor='lm' if position == 'right' else 'rm',
                          stroke_width=1,
                          stroke_fill=TC_NIGHT_BLACK
                          )
                name_grid.fill_box(box)
                return True

        font = self.r.font_small
        for sx, sy, city in labels:
            text = f'{city}'

            if text in label_cache:
                continue
            else:
                label_cache.add(text)

            text_w, text_h = font.getsize(text)
            if not plot_city(text, 'right', sx, sy, text_w, text_h):
                plot_city(text, 'left', sx, sy, text_w, text_h)

        return pic


class BondRuler:
    def __init__(self, loc: BaseLocalization, data: NetworkNodeIpInfo, width=800):
        self.data = data
        self.width = width
        self.loc = loc

    def generate(self, d: ImageDraw, x, y):
        bond_min, bond_med, bond_max, bond_total = self.data.get_min_median_max_total_bond(self.data.active_nodes)
        bond_upper_bound = math.ceil(bond_max / 500_000) * 500_000 + 100_000
        bond_lower_bound = 300_000 if bond_min > 300_000 else 0
        color = '#147e73'
        w = self.width
        line_width = 3
        r = ResourcesNodePic()

        d.line(((x, y), (x + w, y)), fill=color, width=line_width)

        def x_coord(bond):
            return linear_transform(bond, bond_lower_bound, bond_upper_bound, x, x + w)

        loc = self.loc

        notches = [
            (bond_lower_bound, 20, 'mm', ''),
            (bond_min, 17, 'mm', loc.TEXT_PIC_MIN_BOND),
            (bond_med, 17, 'mm', loc.TEXT_PIC_MEDIAN_BOND),
            (bond_max, 17, 'mm', loc.TEXT_PIC_MAX_BOND),
            (bond_upper_bound, 20, 'mm', '')
        ]
        for bond, h_n, anch, label in notches:
            x_n = x_coord(bond)
            line_color = color if not label else TC_YGGDRASIL_GREEN
            d.line(((x_n, y - h_n), (x_n, y + h_n)), fill=line_color, width=line_width)
            d.text((x_n, y + 48), short_rune(bond), font=r.font_small, fill=line_color, anchor=anch)
            if label:
                d.text((x_n, y - 44), label, font=r.font_norm, fill=TC_WHITE, anchor='mm')

        d.rectangle([
            (x_coord(bond_min), y - 6),
            (x_coord(bond_max), y + 6)
        ], fill=TC_YGGDRASIL_GREEN)


class NodePictureGenerator:
    # todo: twitter aspect must be 16:9?
    PIC_WIDTH = 2000
    PIC_HEIGHT = 1800
    RESAMPLE_TIME = '1d'
    MAX_CATEGORIES = 5
    CHART_PERIOD = 30 * DAY

    @staticmethod
    def proper_name():
        return f'THORChain-world-{today_str()}.png'

    def __init__(self, data: NetworkNodeIpInfo, node_stats_points: List[NodeStatsItem],
                 loc: BaseLocalization, max_categories=MAX_CATEGORIES):
        self.data = data
        self.node_stats_points = node_stats_points
        self.loc = loc
        self.max_categories = max_categories

    def _categorize(self, items, active_nodes):
        # [(NAME, count)]
        counted_items = most_common_and_other(items, self.max_categories, self.category_other)

        # {IP: (NAME, color)}
        color_map = {}
        colors = {prov_name: self.index_to_color(i) for i, (prov_name, _) in enumerate(counted_items)}
        for prov_name, node in zip(items, active_nodes):
            if node.ip_address:
                color_map[node.ip_address] = (prov_name, colors.get(prov_name, colors.get(self.category_other)))
        return color_map, counted_items

    @staticmethod
    def index_to_color(i):
        return get_palette_color_by_index(i, TC_PALETTE)

    @async_wrap
    def generate(self):
        active_nodes = self.data.active_nodes
        providers_all = self.data.get_providers(self.data.node_info_list, unknown=self.loc.TEXT_PIC_UNKNOWN)
        providers = self.data.get_providers(active_nodes, unknown=self.loc.TEXT_PIC_UNKNOWN)
        countries = self.data.get_countries(active_nodes, unknown=self.loc.TEXT_PIC_UNKNOWN)

        _, counted_providers = self._categorize(providers, active_nodes)
        color_map_providers, _ = self._categorize(providers_all, self.data.node_info_list)
        color_map_countries, counted_countries = self._categorize(countries, active_nodes)

        # build the image
        r = ResourcesNodePic()
        w, h = self.PIC_WIDTH, self.PIC_HEIGHT
        image = default_background(w, h)
        draw = ImageDraw.Draw(image)

        # world map
        world = WorldMap(self.loc)
        big_map = world.draw(self.data, color_map_providers)
        big_map.thumbnail((w, h), Image.ANTIALIAS)
        image.paste(big_map, (0, 80))

        donut_y = 1020
        legend_y = 1440
        donut_cloud_x = 60
        donut_country_x = 1560

        # Cloud distribution of active nodes
        donut_cloud = self._make_donut(r, counted_providers, 400, self.loc.TEXT_PIC_CLOUD)
        image.paste(donut_cloud, (donut_cloud_x, donut_y), donut_cloud)
        plot_legend(draw,
                    [e[0] for e in counted_providers],
                    (donut_cloud_x, legend_y),
                    font=r.font_small, max_width=440, palette=self.index_to_color)

        # Countries distribution of active nodes
        donut_country = self._make_donut(r, counted_countries, 400, self.loc.TEXT_PIC_COUNTRY)
        image.paste(donut_country, (donut_country_x, donut_y), donut_country)
        plot_legend(draw,
                    [e[0] for e in counted_countries],
                    (donut_country_x, legend_y),
                    font=r.font_small, max_width=440, palette=self.index_to_color)

        # Stats
        self._make_node_stats(draw, r, 700, 1050)

        # Ruler
        ruler_margin = 142
        br = BondRuler(self.loc, self.data, self.PIC_WIDTH - ruler_margin * 2)
        br.generate(draw, ruler_margin, 1680)

        # TC Logo
        logo_x, logo_y = 30, 22
        image.paste(r.tc_logo, (logo_x, logo_y))
        draw.text((logo_x + 10 + r.tc_logo.width, 81),
                  self.loc.TEXT_PIC_NODES, fill=TC_WHITE,
                  font=r.fonts.get_font(44), anchor='lb')

        # Chart
        chart = self._make_bond_chart(self.node_stats_points, r, 900, 450, period=self.CHART_PERIOD)
        image.paste(chart, (580, 1150), chart)

        return image

    def _make_node_stats(self, draw, r: ResourcesNodePic, x, y):
        bond_min, bond_med, bond_max, bond_total = self.data.get_min_median_max_total_bond(self.data.active_nodes)

        anchor = 'mt'

        font_subtitle = r.fonts.get_font(44)
        font_subtitle_bold = r.fonts.get_font(44, r.fonts.FONT_BOLD)
        font_head = r.fonts.get_font(80)
        font_head_bold = r.fonts.get_font(80, r.fonts.FONT_BOLD)

        def render_text(title, value, value2, _x, _y, big, color, stroke=False):
            draw.text((_x, _y), str(title), font=r.font_norm, fill=TC_WHITE, anchor=anchor)
            if stroke:
                f = font_head_bold if big else font_subtitle_bold
            else:
                f = font_head if big else font_subtitle
            draw.text((_x, _y + 40), str(value), font=f, fill=color, anchor=anchor,
                      stroke_fill=TC_WHITE)
            if value2:
                draw.text((_x, _y + 80), str(value2), font=r.font_small, fill="#bfd", anchor=anchor,
                          )

        dx = 240

        render_text(self.loc.TEXT_PIC_ACTIVE_NODES, len(self.data.active_nodes),
                    None, x + dx * 0, y, True, TC_LIGHTNING_BLUE, stroke=True)

        bond_percent_str = bracketify(format_percent(bond_total, self.data.total_rune_supply))
        render_text(self.loc.TEXT_PIC_ACTIVE_BOND, short_rune(bond_total), bond_percent_str, x + dx * 1, y, False,
                    TC_YGGDRASIL_GREEN, stroke=True)

        bond_all_total = self.data.total_bond
        bond_percent_str = bracketify(format_percent(bond_all_total, self.data.total_rune_supply))

        render_text(self.loc.TEXT_PIC_TOTAL_NODES, len(self.data.node_info_list), None, x + dx * 2, y, True,
                    TC_LIGHTNING_BLUE)
        render_text(self.loc.TEXT_PIC_TOTAL_BOND, short_rune(bond_all_total), bond_percent_str, x + dx * 3, y, False,
                    TC_YGGDRASIL_GREEN)

    @property
    def category_other(self):
        return self.loc.TEXT_PIC_OTHERS

    def _make_donut(self, r, elements, width, title):
        donut1 = make_donut_chart(elements,
                                  line_width=200,
                                  font_abs_count=r.font_norm,
                                  label_r=184,
                                  width=width,
                                  margin=44,
                                  palette=self.index_to_color,
                                  title_color='white', font_middle=r.font_subtitle, title=title)
        return donut1

    @staticmethod
    def sparse_points(pts, interval=DAY):
        results = []
        last_ts = None
        for p in reversed(pts):
            if last_ts is None or abs(p.ts - last_ts) >= interval:
                results.append(p)
                last_ts = p.ts

        return list(reversed(results))

    def _make_bond_chart(self, pts: List[NodeStatsItem], r, w, h, period=DAY * 14):
        gr = PlotGraphLines(w, h, bg=(0, 0, 0, 0))
        gr.x_formatter = gr.date_formatter
        gr.y_formatter = short_rune
        gr.n_ticks_y = 4
        gr.n_ticks_x = 6
        gr.axis_text_color = '#888'
        gr.margin = 20
        gr.left = 120
        gr.font_ticks = r.font_small
        gr.grid_lines = True
        gr.bar_height_limit = 142

        if pts:
            pts = self.sparse_points(pts)
            bond_points = [(p.ts, p.bond_active_total) for p in pts]
            node_points = [(p.ts, p.n_active_nodes) for p in pts]

            gr.add_series(bond_points, TC_YGGDRASIL_GREEN)
            # gr.add_series(node_points, TC_LIGHTNING_BLUE)
            # TC_MIDGARD_TURQOISE
            gr.add_series_bars(node_points, TC_LIGHTNING_BLUE, 6, show_values=3)
            gr.update_bounds()
            gr.min_y = 0.0
            gr.max_y *= 1.1

        gr.min_x = now_ts() - period
        gr.max_x = now_ts()
        return gr.finalize()
