import random

from PIL import ImageDraw, ImageFont, Image

from localization.eng_base import BaseLocalization
from services.lib.draw_utils import generate_gradient
from services.lib.plot_graph import PlotGraph
from services.lib.utils import async_wrap, Singleton
from services.models.node_info import NetworkNodeIpInfo


class Resources(metaclass=Singleton):
    BASE = './data'
    WORLD_FILE = f'{BASE}/8081_earthmap2k.jpg'

    FONT_BOLD = f'{BASE}/my.ttf'

    def __init__(self) -> None:
        self.font_large = ImageFont.truetype(self.FONT_BOLD, 68)
        self.font_head = ImageFont.truetype(self.FONT_BOLD, 48)
        self.font_subtitle = ImageFont.truetype(self.FONT_BOLD, 34)
        self.font_small = ImageFont.truetype(self.FONT_BOLD, 22)
        self.font_norm = ImageFont.truetype(self.FONT_BOLD, 28)

        self.world_map = Image.open(self.WORLD_FILE)


class WorldMap:
    def __init__(self):
        self.pic = Resources().world_map.copy()

    def draw(self, data: NetworkNodeIpInfo) -> Image:
        draw = ImageDraw.Draw(self.pic)
        w, h = self.pic.size

        cache = set()

        for node in data.node_info_list:
            if node.is_active:
                geo = data.ip_info_dict[node.ip_address]
                lat, long = geo.get('latitude'), geo.get('longitude')
                if not lat or not long:
                    lat, long = 90, 0
                x = (long + 180.0) / 360.0 * w
                y = (90.0 - lat) / 180.0 * h
                key = f'{x}-{y}'
                if key in cache:
                    x += w * random.uniform(-0.01, 0.01)
                    y += h * random.uniform(-0.01, 0.01)
                cache.add(key)

                draw.ellipse([(x - 5, y - 5), (x + 5, y + 5)], fill='#22ff11')

        return self.pic


class NodePictureGenerator:
    PIC_WIDTH = 1024
    PIC_HEIGHT = 768

    def __init__(self, data: NetworkNodeIpInfo, loc: BaseLocalization):
        self.data = data
        self.loc = loc
        self.max_categories = 3

    @async_wrap
    def generate(self):
        w, h = self.PIC_WIDTH, self.PIC_HEIGHT
        image = generate_gradient(PlotGraph.GRADIENT_TOP_COLOR, PlotGraph.GRADIENT_BOTTOM_COLOR, w, h)

        world = WorldMap()
        big_map = world.draw(self.data)

        big_map.thumbnail((w - 20, h), Image.ANTIALIAS)
        image.paste(big_map, (10, 10))

        return image
