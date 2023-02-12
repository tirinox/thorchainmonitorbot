import datetime
import os.path
import random

from PIL import Image, ImageDraw

from localization.achievements.ach_eng import AchievementsEnglishLocalization
from services.dialog.picture.common import BasePictureGenerator
from services.dialog.picture.resources import Resources
from services.jobs.achievement.ach_list import Achievement
from services.lib.date_utils import today_str
from services.lib.draw_utils import pos_percent, paste_image_masked, measure_font_to_fit_in_box
from services.lib.utils import async_wrap


class AchievementPictureGenerator(BasePictureGenerator):
    BASE = './data/achievement'
    WIDTH = 1024
    HEIGHT = 1024

    PICTURE_BACKGROUNDS = [
        'nn_wreath_1.png',
        'nn_wreath_2.png',
        'nn_wreath_3.png',
        'nn_wreath_4.png',
        'nn_wreath_5.png',
    ]

    PICTURE_BACKGROUND_ANNIVERSARY = 'nn_wreath_ann_2.png'

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

    def get_bg(self, attributes):
        path = os.path.join(self.BASE, attributes['background'])
        image = Image.open(path)
        return image

    @async_wrap
    def _get_picture_sync(self):
        _desc, ago, desc_text, emoji, milestone_str, prev_milestone_str, value_str = self.loc.prepare_achievement_data(
            self.ach,
            newlines=True,
        )
        desc_text = desc_text.upper()

        # ---- Canvas ----
        r = Resources()
        attributes = self.custom_attributes(r)  # for this kind of achievement
        image = self.get_bg(attributes)
        draw = ImageDraw.Draw(image)
        font_getter = r.fonts.get_font
        font_getter_bold = r.fonts.get_font_bold

        logo_y = 6
        main_number_y = 46
        desc_y = 89

        # ---- Logo ----
        paste_image_masked(image, r.tc_logo_transparent, self.pos_percent(50, logo_y), 'mm')
        # paste_image_masked(image, r.tc_logo_transparent, self.pos_percent(2, 2), 'lt')

        # ---- Main number ----

        mx, my = self.pos_percent(50, main_number_y)

        main_number_label = attributes['main_font'].render_string(milestone_str)
        main_number_label.thumbnail(attributes['main_area'])
        paste_image_masked(image, main_number_label, (mx, my))

        # ---- Description ----
        desc_color = attributes['desc_color']
        font_desc, *_ = measure_font_to_fit_in_box(font_getter_bold, desc_text, 890, 172, current_font_size=80)

        desc_pos = self.pos_percent(50, desc_y)
        draw.text(desc_pos, desc_text,
                  fill=desc_color,
                  font=font_desc,
                  stroke_fill='#000',
                  stroke_width=10,
                  anchor='mm', align='center')
        draw.text(desc_pos, desc_text,
                  fill=desc_color,
                  font=font_desc,
                  stroke_fill=attributes['desc_stroke'],
                  stroke_width=2,
                  anchor='mm', align='center')

        # ---- Date ----
        date_str = datetime.datetime.fromtimestamp(self.ach.timestamp).strftime('%B %d, %Y')
        date_str = date_str.upper()
        draw.text(self.pos_percent(50, 99), date_str,
                  fill='#aaa', font=font_getter(28), anchor='mb')

        return image

    async def prepare(self):
        return await super().prepare()

    def custom_attributes(self, r):
        if self.ach.key == Achievement.ANNIVERSARY:
            bg = self.PICTURE_BACKGROUND_ANNIVERSARY
            main_font = r.custom_font_balloon
            main_colors = ['#fff5b5', '#f211be', '#83acea']
            desc_color = '#f4e18d'
            desc_stroke = '#954c07'
            main_area = (320, 320)
        else:
            bg = random.choice(self.PICTURE_BACKGROUNDS)
            main_font = r.custom_font_runic
            main_colors = ['#ecfffc', '#1f756a', '#82e6d1']
            desc_color = '#fff'
            desc_stroke = '#1f756a'
            main_area = (290, 280)

        return {
            'main_font': main_font,
            'main_colors': main_colors,
            'background': bg,
            'desc_color': desc_color,
            'desc_stroke': desc_stroke,
            'main_area': main_area,
        }
