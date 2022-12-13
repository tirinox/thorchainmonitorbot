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

        image = Image.new('RGBA', (w, h), bg_color)

        draw = ImageDraw.Draw(image)

        r = Resources()
        text = short_money(self.rec.milestone, integer=True)
        main_font = r.fonts.get_font_bold(90)
        draw.text(self.pos_percent(50, 50), text, fill=TC_WHITE, font=main_font, anchor='mm')

        font_desc = r.fonts.get_font(52)
        draw.text(self.pos_percent(50, 80), str(self.rec.key), fill=TC_WHITE, font=font_desc, anchor='mm')

        return image

    async def prepare(self):
        return await super().prepare()
