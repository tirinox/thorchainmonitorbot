import datetime
import os.path

from PIL import Image, ImageDraw

from localization.achievements.ach_eng import AchievementsEnglishLocalization
from services.dialog.picture.common import BasePictureGenerator
from services.dialog.picture.resources import Resources
from services.jobs.achievements import Achievement
from services.lib.date_utils import today_str
from services.lib.draw_utils import pos_percent, paste_image_masked, measure_font_to_fit_in_box
from services.lib.utils import async_wrap


class AchievementPictureGenerator(BasePictureGenerator):
    BASE = './data/achievement'
    WIDTH = 1024
    HEIGHT = 1024

    BG_DEFAULT = 'nn_wreath_2.png'
    BG_SPECIAL = {
        Achievement.ANNIVERSARY: 'nn_wreath_ann_2.png',
    }

    def generate_picture_filename(self):
        return f'thorchain-ach-{self.ach.key}-{today_str()}.png'

    def __init__(self, loc: AchievementsEnglishLocalization, a: Achievement):
        # noinspection PyTypeChecker
        super().__init__(loc)
        self.loc = loc
        self.ach = a
        self.w = self.WIDTH
        self.h = self.HEIGHT

    def pos_percent(self, px, py):
        return pos_percent(px, py, w=self.w, h=self.h)

    def get_bg(self):
        name = self.BG_SPECIAL.get(self.ach.key, self.BG_DEFAULT)
        return os.path.join(self.BASE, name)

    @async_wrap
    def _get_picture_sync(self):
        _desc, ago, desc_text, emoji, milestone_str, prev_milestone_str, value_str = self.loc.prepare_achievement_data(
            self.ach,
            newlines=True,
        )
        desc_text = desc_text.upper()

        # ---- Canvas ----
        r = Resources()
        image = Image.open(self.get_bg())
        draw = ImageDraw.Draw(image)
        font_getter = r.fonts.get_font
        font_getter_bold = r.fonts.get_font_bold
        font_getter_main = self.main_number_font_getter(r)

        logo_y = 6
        main_number_y = 46
        desc_y = 89

        main_colors = self.main_colors()
        stroke_step = 4

        # ---- Logo ----
        paste_image_masked(image, r.tc_logo_transparent, self.pos_percent(50, logo_y), 'mm')
        # paste_image_masked(image, r.tc_logo_transparent, self.pos_percent(2, 2), 'lt')

        # ---- Main number ----

        # text = achievement_desc.format_value(self.ach.milestone, self.ach)

        main_font, mw, mh = measure_font_to_fit_in_box(font_getter_main, milestone_str, 270, 280)
        mx, my = self.pos_percent(50, main_number_y)

        fill_color = main_colors[0]
        main_colors = main_colors[1:]
        start_stroke = (len(main_colors)) * stroke_step
        for outline_color, stroke in zip(reversed(main_colors), range(start_stroke, 0, -stroke_step)):
            draw.text((mx, my), milestone_str, fill=fill_color,
                      font=main_font, anchor='mm', stroke_fill=outline_color, stroke_width=stroke)

        # ---- Description ----
        desc_color = '#fff'
        font_desc, *_ = measure_font_to_fit_in_box(font_getter_bold, desc_text, 890, 172, current_font_size=80)

        draw.text(self.pos_percent(50, desc_y), desc_text,
                  fill=desc_color,
                  font=font_desc,
                  # stroke_fill='#000',
                  stroke_fill='#1f756a',
                  stroke_width=2,
                  anchor='mm', align='center')

        # ---- Date ----
        date_str = datetime.datetime.fromtimestamp(self.ach.timestamp).strftime('%B %d, %Y')
        date_str = date_str.upper()
        draw.text(self.pos_percent(50, 99), date_str, fill='#aaa', font=font_getter(28), anchor='mb',
                  # stroke_fill=main_outlines[0], stroke_width=2
                  )

        return image

    async def prepare(self):
        return await super().prepare()

    def main_colors(self):
        if self.ach.key == Achievement.ANNIVERSARY:
            return ['#fff5b5', '#f211be', '#83acea']
        else:
            return ['#ecfffc', '#1f756a', '#82e6d1']

    def main_number_font_getter(self, r):
        if self.ach.key == Achievement.ANNIVERSARY:
            return r.fonts.get_font_bold
        else:
            return r.fonts.get_font_norse_bold