from PIL import ImageDraw, ImageFont

from localization.eng_base import BaseLocalization
from services.lib.draw_utils import generate_gradient
from services.lib.plot_graph import PlotGraph
from services.lib.utils import async_wrap, Singleton
from services.models.node_info import NetworkNodeIpInfo


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

        r = Resources()
        draw = ImageDraw.Draw(image)

        cx = image.width // 2

        return image
