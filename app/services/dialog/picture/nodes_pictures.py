import math
import random

from PIL import ImageFont, Image, ImageDraw

from localization.eng_base import BaseLocalization
from services.lib.draw_utils import default_background, CacheGrid, TC_YGGDRASIL_GREEN, \
    make_donut_chart, TC_NIGHT_BLACK, get_palette_color_by_index_new, \
    TC_PALETTE, TC_WHITE
from services.lib.money import clamp, short_rune, format_percent
from services.lib.plot_graph import plot_legend
from services.lib.texts import bracketify
from services.lib.utils import async_wrap, Singleton, most_common_and_other, linear_transform
from services.models.node_info import NetworkNodeIpInfo


class Resources(metaclass=Singleton):
    BASE = './data'
    # WORLD_FILE = f'{BASE}/8081_earthmap2k.jpg'
    WORLD_FILE = f'{BASE}/earth-bg.png'
    LOGO_FILE = f'{BASE}/tc_logo.png'
    CIRCLE_FILE = f'{BASE}/circle_new.png'
    CIRCLE_DIM_FILE = f'{BASE}/circle-dim.png'

    FONT_BOLD = f'{BASE}/my.ttf'

    def __init__(self) -> None:
        self.font_small = ImageFont.truetype(self.FONT_BOLD, 30)
        self.font_norm = ImageFont.truetype(self.FONT_BOLD, 34)
        self.font_large = ImageFont.truetype(self.FONT_BOLD, 40)
        self.font_subtitle = ImageFont.truetype(self.FONT_BOLD, 44)
        self.font_head = ImageFont.truetype(self.FONT_BOLD, 60)

        self.world_map = Image.open(self.WORLD_FILE)
        self.tc_logo = Image.open(self.LOGO_FILE)
        self.circle = Image.open(self.CIRCLE_FILE)
        self.circle_dim = Image.open(self.CIRCLE_DIM_FILE)


class WorldMap:
    def __init__(self, loc: BaseLocalization):
        self.r = Resources()
        self.w, self.h = self.r.world_map.size
        self.loc = loc
        self.lable_color = TC_WHITE

    def convert_coord_to_xy(self, long, lat):
        x = (long + 180.0) / 360.0 * self.w
        y = (90.0 - lat) / 180.0 * self.h
        return x, y

    def draw(self, data: NetworkNodeIpInfo, color_map) -> Image:
        # color_map: ip_address => (prov_name, color)
        data.sort_by_status()
        pic = self.r.world_map.copy()
        w, h = pic.size

        draw = ImageDraw.Draw(pic)

        coord_cache = set()
        lable_cache = set()

        randomize_factor = 0.0025
        max_point_size = 50
        min_point_size = 1
        n_unknown_nodes = 0

        name_grid = CacheGrid(40, 60)

        unk_lat, unk_long = -60, 0
        name_grid.set(*self.convert_coord_to_xy(unk_long, unk_lat))

        countries = []
        labels = []

        for node in data.node_info_list:
            geo = data.ip_info_dict.get(node.ip_address, {})
            lat, long = geo.get('latitude'), geo.get('longitude')

            country = geo.get('country_name')
            city = geo.get('city')
            if country:
                countries.append(country)

            if not lat or not long:
                if node.is_active:
                    lat, long = unk_lat, unk_long
                    n_unknown_nodes += 1
                else:
                    continue

            x, y = self.convert_coord_to_xy(long, lat)
            key = f'{x}-{y}'
            if key in coord_cache:
                x += w * random.uniform(-randomize_factor, randomize_factor)
                y += h * random.uniform(-randomize_factor, randomize_factor)
            else:
                labels.append((x, y, city))

            coord_cache.add(key)

            point_size = ((node.bond / 1e6) ** 2) * max_point_size
            point_size = int(math.ceil(clamp(point_size, min_point_size, max_point_size)))
            point_size_half = point_size // 2

            source_image = self.r.circle if node.is_active else self.r.circle_dim

            point_image = source_image.copy()
            point_image.thumbnail((point_size, point_size), Image.ANTIALIAS)

            x, y = int(x), int(y)
            # pic.paste(point_image, (x - point_size_half, y - point_size_half), point_image)

            color = color_map.get(node.ip_address, (0, TC_WHITE))[1]

            point_size_half = int(point_size_half * 0.7)
            draw.ellipse((
                (x - point_size_half, y - point_size_half),
                (x + point_size_half, y + point_size_half),
            ), fill=color, outline='#000')

        label_x_shift = 30
        if n_unknown_nodes:
            x, y = self.convert_coord_to_xy(unk_long, unk_lat)
            draw.text((x + label_x_shift, y),
                      f'Unknown location ({n_unknown_nodes})',  # todo: localize
                      fill='#005566',
                      font=self.r.font_small, anchor='lm')

        font = self.r.font_small
        for sx, sy, city in labels:
            text = f'{city}'

            if text in lable_cache:
                continue
            else:
                lable_cache.add(text)

            w, h = font.getsize(text)
            # right position
            box = (sx + label_x_shift, sy - h // 2), (sx + label_x_shift + w, sy + h // 2)
            if not name_grid.is_box_occupied(box):
                draw.text((sx + label_x_shift, sy),
                          text,
                          fill=self.lable_color,
                          font=self.r.font_small,
                          anchor='lm',
                          stroke_width=2,
                          stroke_fill=TC_NIGHT_BLACK)
                name_grid.fill_box(box)
            else:
                # left position
                box = (sx - label_x_shift - w, sy - h // 2), (sx - label_x_shift, sy + h // 2)
                if not name_grid.is_box_occupied(box):
                    draw.text((sx - label_x_shift, sy),
                              text,
                              fill=self.lable_color,
                              font=self.r.font_small,
                              anchor='rm',
                              stroke_width=1,
                              stroke_fill=TC_NIGHT_BLACK)
                    name_grid.fill_box(box)

        return pic


class BondRuler:
    def __init__(self, data: NetworkNodeIpInfo, width=800):
        self.data = data
        self.width = width

    def generate(self, d: ImageDraw, x, y):
        bond_min, bond_med, bond_max, bond_total = self.data.get_min_median_max_total_bond(self.data.active_nodes)
        bond_upper_bound = math.ceil(bond_max / 1e6) * 1e6 + 0.1e6
        bond_lower_bound = 0.3e6
        color = '#147e73'
        w = self.width
        line_width = 3
        r = Resources()

        d.line(((x, y), (x + w, y)), fill=color, width=line_width)

        def x_coord(bond):
            return linear_transform(bond, bond_lower_bound, bond_upper_bound, x, x + w)

        notches = [
            (bond_lower_bound, 20, 'mm', ''),
            (bond_min, 17, 'mm', 'Min bond'),
            (bond_med, 17, 'mm', 'Median'),
            (bond_max, 17, 'mm', 'Max'),
            (bond_upper_bound, 20, 'mm', '')
        ]
        for bond, h_n, anch, label in notches:
            x_n = x_coord(bond)
            d.line(((x_n, y - h_n), (x_n, y + h_n)), fill=color, width=line_width)
            d.text((x_n, y + 48), short_rune(bond), font=r.font_small, fill=TC_YGGDRASIL_GREEN, anchor=anch)
            if label:
                d.text((x_n, y - 44), label, font=r.font_norm, fill=TC_WHITE, anchor='mm')

        d.rectangle([
            (x_coord(bond_min), y - 6),
            (x_coord(bond_max), y + 6)
        ], fill=color)


class NodePictureGenerator:
    PIC_WIDTH = 2000
    PIC_HEIGHT = 1800

    def __init__(self, data: NetworkNodeIpInfo, loc: BaseLocalization):
        self.data = data
        self.loc = loc
        self.max_categories = 5

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
        return get_palette_color_by_index_new(i, TC_PALETTE, step=1.0)

    @async_wrap
    def generate(self):
        active_nodes = self.data.active_nodes
        providers = self.data.get_providers(active_nodes, unknown=self.loc.TEXT_PIC_UNKNOWN)
        countries = self.data.get_countries(active_nodes, unknown=self.loc.TEXT_PIC_UNKNOWN)

        color_map_providers, counted_providers = self._categorize(providers, active_nodes)
        color_map_countries, counted_countries = self._categorize(countries, active_nodes)

        # build the image
        r = Resources()
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
        donut_cloud = self._make_donut(r, counted_providers, 400, 'Cloud')
        image.paste(donut_cloud, (donut_cloud_x, donut_y), donut_cloud)
        plot_legend(draw,
                    [e[0] for e in counted_providers],
                    (donut_cloud_x, legend_y),
                    font=r.font_small, max_width=440, palette=self.index_to_color)

        # Countries distribution of active nodes
        donut_country = self._make_donut(r, counted_countries, 400, 'Country')
        image.paste(donut_country, (donut_country_x, donut_y), donut_country)
        plot_legend(draw,
                    [e[0] for e in counted_countries],
                    (donut_country_x, legend_y),
                    font=r.font_small, max_width=440, palette=self.index_to_color)

        # Stats
        self._make_node_stats(draw, r, 800, 1050, 90)

        # Ruler
        ruler_margin = 142
        br = BondRuler(self.data, self.PIC_WIDTH - ruler_margin * 2)
        br.generate(draw, ruler_margin, 1680)

        # TC Logo
        image.paste(r.tc_logo, ((w - r.tc_logo.size[0]) // 2, 10))

        return image

    def _make_node_stats(self, draw, r, x, y, dy):
        bond_min, bond_med, bond_max, bond_total = self.data.get_min_median_max_total_bond(self.data.active_nodes)

        def render_text(title, value, value2, _x, _y):
            draw.text((_x, _y), str(title), font=r.font_small, fill=TC_WHITE, anchor='lt')
            draw.text((_x, _y + 33), str(value), font=r.font_subtitle, fill=TC_YGGDRASIL_GREEN, anchor='lt')
            if value2:
                draw.text((_x, _y + 72), str(value2), font=r.font_small, fill="#bfd", anchor='lt')

        bond_percent_str = bracketify(format_percent(bond_total, self.data.total_rune_supply))
        render_text(f'Active bond', short_rune(bond_total), bond_percent_str, x, y)

        bond_all_total = self.data.total_bond
        bond_percent_str = bracketify(format_percent(bond_all_total, self.data.total_rune_supply))
        render_text(f'Total bond', short_rune(bond_all_total), bond_percent_str, x + 260, y)

        render_text('Active nodes', len(self.data.active_nodes), None, x + 0, y + 150)
        render_text('Total nodes', len(self.data.node_info_list), None, x + 260, y + 150)

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
