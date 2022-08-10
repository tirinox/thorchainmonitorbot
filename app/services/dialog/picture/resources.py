from PIL import Image, ImageFont

from services.dialog.picture.crypto_logo import CryptoLogoDownloader
from services.lib.utils import Singleton


class Resources(metaclass=Singleton):
    BASE = './data'
    LOGO_BASE = './data/asset_logo'
    LOGO_WIDTH, LOGO_HEIGHT = 128, 128
    HIDDEN_IMG = f'{BASE}/hidden.png'
    BG_IMG = f'{BASE}/lp_bg.png'

    FONT_BOLD = f'{BASE}/my.ttf'

    def __init__(self) -> None:
        self.hidden_img = Image.open(self.HIDDEN_IMG)
        self.hidden_img.thumbnail((200, 36))

        self.font = ImageFont.truetype(self.FONT_BOLD, 40)
        self.font_head = ImageFont.truetype(self.FONT_BOLD, 48)
        self.font_small = ImageFont.truetype(self.FONT_BOLD, 28)
        self.font_semi = ImageFont.truetype(self.FONT_BOLD, 36)
        self.font_big = ImageFont.truetype(self.FONT_BOLD, 64)
        self.bg_image = Image.open(self.BG_IMG)

        self.logo_downloader = CryptoLogoDownloader(self.LOGO_BASE)

        self.font_sum_ticks = ImageFont.truetype(self.FONT_BOLD, 24)

    def put_hidden_plate(self, image, position, anchor='left', ey=-3):
        x, y = position
        if anchor == 'right':
            x -= self.hidden_img.width
        elif anchor == 'center':
            x -= self.hidden_img.width // 2
        y -= self.hidden_img.height + ey
        image.paste(self.hidden_img, (x, y), self.hidden_img)
