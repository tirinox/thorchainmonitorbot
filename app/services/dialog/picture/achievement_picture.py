import datetime
import os.path

from PIL import Image, ImageDraw

from localization.achievements.ach_eng import AchievementsEnglishLocalization
from services.dialog.picture.common import BasePictureGenerator
from services.dialog.picture.resources import Resources
from services.jobs.achievements import AchievementRecord
from services.lib.date_utils import today_str
from services.lib.draw_utils import pos_percent, TC_WHITE
from services.lib.money import short_money
from services.lib.utils import async_wrap


class AchievementPictureGenerator(BasePictureGenerator):
    BASE = './data'
    WIDTH = 512
    HEIGHT = 512

    BG = 'tc-achievement-bg-1.png'

    def generate_picture_filename(self):
        return f'thorchain-ach-{self.rec.key}-{today_str()}.png'

    def __init__(self, loc: AchievementsEnglishLocalization, rec: AchievementRecord):
        # noinspection PyTypeChecker
        super().__init__(loc)
        self.loc = loc
        self.rec = rec
        self.w = self.WIDTH
        self.h = self.HEIGHT

    def pos_percent(self, px, py):
        return pos_percent(px, py, w=self.w, h=self.h)

    @async_wrap
    def _get_picture_sync(self):
        # steps:
        # 1. make background
        # 2. format the number (proper size, etc)
        # 3. format the explanatory text (proper size, etc)
        # 5. date and time elapsed from the past milestone
        w, h = self.WIDTH, self.HEIGHT
        bg_color = (0, 0, 0, 255)

        # image = Image.new('RGBA', (w, h), bg_color)
        image = Image.open(os.path.join(self.BASE, self.BG))

        draw = ImageDraw.Draw(image)

        r = Resources()
        text = short_money(self.rec.milestone, integer=True)
        main_font, mw, mh = self.detect_font_size(r.fonts.get_font_bold, text, 460, 240)
        mx, my = self.pos_percent(50, 45)
        draw.text((mx, my), text, fill=TC_WHITE, font=main_font, anchor='mm')

        # pillow get font size from bounding box

        desc_text = self.loc.get_achievement_description(self.rec.key).description
        font_desc, *_ = self.detect_font_size(r.fonts.get_font, desc_text, 400, 120)
        draw.text((mx, my + mh // 2 + 20), str(desc_text), fill=TC_WHITE, font=font_desc, anchor='mt')

        date_str = datetime.datetime.fromtimestamp(self.rec.timestamp).strftime('%B %d, %Y')
        draw.text(self.pos_percent(50, 94), date_str, fill=TC_WHITE, font=r.fonts.get_font(30), anchor='mm')

        return image

    def detect_font_size(self, font_getter, text, max_width, max_height, current_font_size=None, f=0.92):
        current_font_size = current_font_size or min(max_width, max_height)

        if current_font_size < 4:
            return None

        font = font_getter(int(current_font_size))
        w, h = font.getsize(text)
        if w > max_width or h > max_height:
            return self.detect_font_size(font_getter, text, max_width, max_height, current_font_size * f)

        return font, w, h

    async def prepare(self):
        return await super().prepare()
