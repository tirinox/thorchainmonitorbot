import math
import random

from PIL import ImageFont, Image, ImageDraw

from localization.eng_base import BaseLocalization
from services.lib.draw_utils import default_background, CacheGrid, TC_LIGHTNING_BLUE, TC_YGGDRASIL_GREEN, \
    make_donut_chart, get_palette_color_by_index, TC_MIDGARD_TURQOISE
from services.lib.money import clamp, short_rune, format_percent
from services.lib.plot_graph import plot_legend
from services.lib.texts import bracketify
from services.lib.utils import async_wrap, Singleton, most_common_and_other
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

        cache = set()

        randomize_factor = 0.005
        max_point_size = 50
        min_point_size = 1
        n_unknown_nodes = 0

        name_grid = CacheGrid(120, 60)

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
            if key in cache:
                x += w * random.uniform(-randomize_factor, randomize_factor)
                y += h * random.uniform(-randomize_factor, randomize_factor)
            else:
                labels.append((x, y, city))

            cache.add(key)

            point_size = node.bond / 1e6 * max_point_size
            point_size = int(math.ceil(clamp(point_size, min_point_size, max_point_size)))
            point_size_half = point_size // 2

            source_image = self.r.circle if node.is_active else self.r.circle_dim

            point_image = source_image.copy()
            point_image.thumbnail((point_size, point_size), Image.ANTIALIAS)

            x, y = int(x), int(y)
            # pic.paste(point_image, (x - point_size_half, y - point_size_half), point_image)

            color = color_map.get(node.ip_address, (0, 'white'))[1]

            point_size_half = int(point_size_half * 0.7)
            draw.ellipse((
                (x - point_size_half, y - point_size_half),
                (x + point_size_half, y + point_size_half),
            ), fill=color, outline='#000')

        label_x_shift = 30
        if n_unknown_nodes:
            x, y = self.convert_coord_to_xy(unk_long, unk_lat)
            draw.text((x + label_x_shift, y),
                      f'Unknown location ({n_unknown_nodes})',
                      fill='#005566',
                      font=self.r.font_small, anchor='lm')

        for sx, sy, city in labels:
            if not name_grid.is_occupied(sx, sy):
                draw.text((sx + label_x_shift, sy), f'{city}', fill=TC_MIDGARD_TURQOISE,
                          font=self.r.font_small, anchor='lm')
                name_grid.set(sx, sy)

        return pic


class NodePictureGenerator:
    PIC_WIDTH = 2048
    PIC_HEIGHT = 1536

    def __init__(self, data: NetworkNodeIpInfo, loc: BaseLocalization):
        self.data = data
        self.loc = loc
        self.max_categories = 5

    @async_wrap
    def generate(self):
        r = Resources()
        w, h = self.PIC_WIDTH, self.PIC_HEIGHT
        image = default_background(w, h)
        draw = ImageDraw.Draw(image)

        providers = self.data.get_providers(self.data.active_nodes)
        providers_counted = self._make_donut_provider(image, draw, r, providers)  # [(PROVIDER, count)]
        colors = {prov_name: get_palette_color_by_index(i) for i, (prov_name, _) in enumerate(providers_counted)}

        color_map = {}
        for prov_name, node in zip(providers, self.data.active_nodes):
            if node.ip_address:
                color_map[node.ip_address] = (prov_name, colors.get(prov_name, colors.get(self.category_other)))

        world = WorldMap(self.loc)
        big_map = world.draw(self.data, color_map)

        big_map.thumbnail((w, h), Image.ANTIALIAS)
        image.paste(big_map, (0, 80))

        self._make_node_stats(draw, r, 20, 400, 80)

        # logo
        image.paste(r.tc_logo, ((w - r.tc_logo.size[0]) // 2, 10))

        return image

    def _make_node_stats(self, draw, r, x, y, dy):
        bond_min, bond_med, bond_max, bond_total = self.data.get_min_median_max_total_bond(self.data.active_nodes)

        def render_text(title, value, value2, _x, _y):
            draw.text((_x, _y), title, font=r.font_small, fill='white', anchor='lt')
            draw.text((_x, _y + 30), value, font=r.font_subtitle, fill=TC_YGGDRASIL_GREEN, anchor='lt')
            if value2:
                draw.text((_x, _y + 68), value2, font=r.font_small, fill=TC_YGGDRASIL_GREEN, anchor='lt')

        render_text(f'Minimum bond', short_rune(bond_min), None, x, y)
        y += dy
        render_text(f'Median bond', short_rune(bond_med), None, x, y)
        y += dy
        render_text(f'Maximum bond', short_rune(bond_max), None, x, y)
        y += dy

        bond_percent_str = bracketify(format_percent(bond_total, self.data.total_rune_supply))
        render_text(f'Total active bond', short_rune(bond_total), bond_percent_str, x, y)

        bond_all_total = self.data.total_bond
        bond_percent_str = bracketify(format_percent(bond_all_total, self.data.total_rune_supply))
        render_text(f'Total bond', short_rune(bond_all_total), bond_percent_str, x, y + dy * 1.5)

    def _make_donut_country(self):
        ...

    @property
    def category_other(self):
        return self.loc.TEXT_PIC_OTHERS

    def _make_donut_provider(self, image, draw, r, providers, width=400):
        providers = [(self.loc.TEXT_PIC_UNKNOWN if p == NetworkNodeIpInfo.UNKNOWN_PROVIDER else p)
                     for p in providers]
        elements = most_common_and_other(providers,
                                         self.max_categories,
                                         self.category_other)

        donut1 = make_donut_chart(elements,
                                  line_width=200,
                                  font_abs_count=r.font_norm,
                                  label_r=180,
                                  width=width,
                                  margin=44,
                                  title_color='white', font_middle=r.font_subtitle, title='Cloud')

        image.paste(donut1, (1000, 1100), donut1)

        plot_legend(draw, [e[0] for e in elements],
                    (1430, 1200),
                    font=r.font_small, max_width=width)

        return elements
