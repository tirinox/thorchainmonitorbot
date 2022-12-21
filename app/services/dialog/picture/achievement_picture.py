import datetime
import os.path

from PIL import Image, ImageDraw

from localization.achievements.ach_eng import AchievementsEnglishLocalization
from services.dialog.picture.common import BasePictureGenerator
from services.dialog.picture.resources import Resources
from services.jobs.achievements import AchievementRecord
from services.lib.date_utils import today_str
from services.lib.draw_utils import pos_percent, TC_MIDGARD_TURQOISE
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
        # w, h = self.WIDTH, self.HEIGHT
        # bg_color = (0, 0, 0, 255)
        # image = Image.new('RGBA', (w, h), bg_color)

        # ---- Canvas ----
        r = Resources()
        image = Image.open(os.path.join(self.BASE, self.BG))
        draw = ImageDraw.Draw(image)

        # ---- Main number ----
        achievement_desc = self.loc.get_achievement_description(self.rec.key)

        text = achievement_desc.format_value(self.rec.milestone)
        main_font, mw, mh = self.detect_font_size(r.fonts.get_font_norse_bold, text, 350, 200)
        mx, my = self.pos_percent(50, 46)

        # or maybe? TC_YGGDRASIL_GREEN, TC_LIGHTNING_BLUE, GOLD_COLOR = (255, 215, 0)
        draw.text((mx, my), text, fill=TC_MIDGARD_TURQOISE,
                  font=main_font, anchor='mm', stroke_fill='#333', stroke_width=4)

        # ---- Description ----
        # pillow get font size from bounding box
        desc_text = achievement_desc.description
        font_desc, *_ = self.detect_font_size(r.fonts.get_font_norse, desc_text, 400, 120)
        draw.text((mx, my + mh // 2 + 32), str(desc_text), fill=(255, 215, 0), font=font_desc, anchor='mt')

        # ---- Date ----
        date_str = datetime.datetime.fromtimestamp(self.rec.timestamp).strftime('%B %d, %Y')
        draw.text(self.pos_percent(50, 91), date_str, fill='#ccc', font=r.fonts.get_font_norse(28), anchor='mm')

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
