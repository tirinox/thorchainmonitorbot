import math
import random

from PIL import ImageFont, Image, ImageDraw

from localization.eng_base import BaseLocalization
from services.lib.draw_utils import default_background
from services.lib.money import clamp
from services.lib.utils import async_wrap, Singleton
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
        self.font_large = ImageFont.truetype(self.FONT_BOLD, 68)
        self.font_head = ImageFont.truetype(self.FONT_BOLD, 48)
        self.font_subtitle = ImageFont.truetype(self.FONT_BOLD, 34)
        self.font_small = ImageFont.truetype(self.FONT_BOLD, 22)
        self.font_norm = ImageFont.truetype(self.FONT_BOLD, 28)

        self.world_map = Image.open(self.WORLD_FILE)
        self.tc_logo = Image.open(self.LOGO_FILE)
        self.circle = Image.open(self.CIRCLE_FILE)
        self.circle_dim = Image.open(self.CIRCLE_DIM_FILE)


class WorldMap:
    def __init__(self):
        self.r = Resources()
        self.w, self.h = self.r.world_map.size

    def convert_coord_to_xy(self, long, lat):
        x = (long + 180.0) / 360.0 * self.w
        y = (90.0 - lat) / 180.0 * self.h
        return x, y

    def draw(self, data: NetworkNodeIpInfo) -> Image:
        data.sort_by_status()
        pic = self.r.world_map.copy()
        w, h = pic.size

        draw = ImageDraw.Draw(pic)

        cache = set()

        randomize_factor = 0.005
        max_point_size = 40
        min_point_size = 1
        n_unknown_nodes = 0

        unk_lat, unk_long = -85, -175

        for node in data.node_info_list:
            geo = data.ip_info_dict.get(node.ip_address, {})
            lat, long = geo.get('latitude'), geo.get('longitude')
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
            cache.add(key)

            point_size = node.bond / 1e6 * max_point_size
            point_size = int(math.ceil(clamp(point_size, min_point_size, max_point_size)))

            source_image = self.r.circle if node.is_active else self.r.circle_dim

            point_image = source_image.copy()
            point_image.thumbnail((point_size, point_size), Image.ANTIALIAS)
            pic.paste(point_image, (int(x) - point_size // 2, int(y) - point_size // 2), point_image)

        if n_unknown_nodes:
            x, y = self.convert_coord_to_xy(unk_long + 3, unk_lat)
            draw.text((x, y),
                      f'Unknown location ({n_unknown_nodes})',
                      fill='white',
                      font=self.r.font_small, anchor='lm')

        return pic


class NodePictureGenerator:
    PIC_WIDTH = 1024
    PIC_HEIGHT = 768

    def __init__(self, data: NetworkNodeIpInfo, loc: BaseLocalization):
        self.data = data
        self.loc = loc
        self.max_categories = 3

    @async_wrap
    def generate(self):
        r = Resources()
        w, h = self.PIC_WIDTH, self.PIC_HEIGHT
        image = default_background(w, h)

        world = WorldMap()
        big_map = world.draw(self.data)

        big_map.thumbnail((w, h), Image.ANTIALIAS)
        image.paste(big_map, (0, 80))

        image.paste(r.tc_logo, ((w - r.tc_logo.size[0]) // 2, 10))

        return image
