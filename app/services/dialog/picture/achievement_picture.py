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

    BG = 'nn_wreath_2.png'

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

    @async_wrap
    def _get_picture_sync(self):
        _desc, ago, desc_text, emoji, milestone_str, prev_milestone_str, value_str = self.loc.prepare_achievement_data(
            self.ach,
            newlines=True,
        )
        desc_text = desc_text.upper()

        # ---- Canvas ----
        r = Resources()
        image = Image.open(os.path.join(self.BASE, self.BG))
        draw = ImageDraw.Draw(image)
        font_getter = r.fonts.get_font
        font_getter_bold = r.fonts.get_font_bold

        logo_y = 8
        main_number_y = 45
        desc_y = 89
        main_color = '#ecfffc'

        main_outlines = [
            '#82e6d1', '#1f756a'
        ]
        stroke_step = 4

        # ---- Logo ----
        paste_image_masked(image, r.tc_logo_transparent, self.pos_percent(50, logo_y), 'mm')

        # ---- Main number ----

        # text = achievement_desc.format_value(self.ach.milestone, self.ach)
        # main_number_color = '#e2d3be'
        main_font, mw, mh = measure_font_to_fit_in_box(font_getter_bold, milestone_str, 300, 280)
        mx, my = self.pos_percent(50, main_number_y)

        start_stroke = (len(main_outlines)) * stroke_step
        for outline_color, stroke in zip(reversed(main_outlines), range(start_stroke, 0, -stroke_step)):
            draw.text((mx, my), milestone_str, fill=main_color,
                      font=main_font, anchor='mm', stroke_fill=outline_color, stroke_width=stroke)

        # ---- Description ----
        desc_color = '#fff'
        font_desc, *_ = measure_font_to_fit_in_box(font_getter_bold, desc_text, 890, 172, current_font_size=80)
        # draw.text((mx - 2, my + mh // 2 + 42 - 2), desc,
        #           fill=(155, 150, 0),
        #           font=font_desc, anchor='mm', align='center')
        draw.text(self.pos_percent(50, desc_y), desc_text,
                  fill=desc_color,
                  font=font_desc,
                  stroke_fill='#000',
                  stroke_width=2,
                  anchor='mm', align='center')

        # ---- Date ----
        date_str = datetime.datetime.fromtimestamp(self.ach.timestamp).strftime('%B %d, %Y')
        date_str = date_str.upper()
        draw.text(self.pos_percent(50, 99), date_str, fill='#ddd', font=font_getter(28), anchor='mb',
                  # stroke_fill='#555', stroke_width=2
                  )

        return image

    async def prepare(self):
        return await super().prepare()
