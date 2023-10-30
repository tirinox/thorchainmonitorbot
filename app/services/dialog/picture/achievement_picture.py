import datetime
import os.path
import random

from PIL import Image, ImageDraw

from localization.achievements.ach_eng import AchievementsLocalizationBase
from services.dialog.picture.common import BasePictureGenerator
from services.dialog.picture.resources import Resources
from services.jobs.achievement.ach_list import Achievement
from services.lib.date_utils import today_str
from services.lib.draw_utils import pos_percent, paste_image_masked, measure_font_to_fit_in_box, convert_indexed_png, \
    add_shadow, add_transparent_frame, add_tint_to_bw_image, adjust_brightness, \
    extract_characteristic_color, draw_text_with_font
from services.lib.utils import async_wrap


class GenericAchievementPictureGenerator(BasePictureGenerator):
    BASE = './data/achievement'
    WIDTH = 1024
    HEIGHT = 1024

    def generate_picture_filename(self):
        return f'thorchain-ach-{self.ach.key}-{today_str()}.png'

    def __init__(self, loc: AchievementsLocalizationBase, a: Achievement, force_background: str = None):
        # noinspection PyTypeChecker
        super().__init__(loc)
        self.loc = loc
        self.ach = a
        self.w = self.WIDTH
        self.h = self.HEIGHT
        self.force_background = force_background
        self.r = Resources()
        self.desc_stroke_width = 4
        self.ach_desc = self.loc.get_achievement_description(self.ach.key)

    def pos_percent(self, px, py):
        return pos_percent(px, py, w=self.w, h=self.h)

    def load_background_picture(self):
        name = self.choice_background()
        path = os.path.join(self.BASE, name)
        image = Image.open(path)
        return convert_indexed_png(image)

    def get_tint(self, image):
        # get dominant color of the background
        tint = extract_characteristic_color(image, threshold=150)
        n = 0
        while sum(tint) < 600 and n < 10:
            tint = adjust_brightness(tint, 1.2)
            n += 1
        return tint

    @async_wrap
    def _get_picture_sync(self):
        desc, ago, desc_text, emoji, milestone_str, prev_milestone_str, value_str = self.loc.prepare_achievement_data(
            self.ach,
            newlines=True,
        )

        bg = self.load_background_picture()

        # get dominant color of the background
        tint = self.get_tint(bg)
        draw = ImageDraw.Draw(bg)
        if desc.custom_attributes:
            attributes = desc.custom_attributes
        else:
            attributes = self.attributes_default(self.r)

        self.put_logo(bg)
        self.put_main_number(bg, attributes, milestone_str, tint, desc)
        self.put_description(attributes, desc_text, bg, tint)
        self.put_date(draw)

        return bg

    def put_date(self, draw):
        font_getter = self.r.fonts.get_font
        date_str = datetime.datetime.fromtimestamp(self.ach.timestamp).strftime('%B %d, %Y')
        date_str = date_str.upper()
        draw.text(self.pos_percent(50, 99), date_str,
                  fill='#aaa', font=font_getter(28), anchor='mb')

    def put_description(self, attributes, desc_text, image, tint):
        desc_text = desc_text.upper()

        desc_y = 89
        font_getter_bold = self.r.fonts.get_font_bold

        desc_color = attributes['desc_color']
        style = attributes['font_style']

        if style == 'fancy':
            desc_color = adjust_brightness(tint, 1.5)

        font_desc, *_ = measure_font_to_fit_in_box(font_getter_bold, desc_text, 890, 172, current_font_size=80)
        desc_pos = self.pos_percent(50, desc_y)
        thick_stroke_color = adjust_brightness(tint, 0.2)
        desc_img = draw_text_with_font(desc_text, font_desc, desc_color)
        desc_img = add_transparent_frame(desc_img, 30)
        shadow_source = add_tint_to_bw_image(desc_img, thick_stroke_color)
        desc_img = add_shadow(desc_img, 20, shadow_source=shadow_source)
        paste_image_masked(image, desc_img, desc_pos)

    def put_main_number(self, image, attributes, milestone_str, tint, desc):
        main_number_y = 48 if desc.more_than else 46

        mx, my = self.pos_percent(50, main_number_y)

        main_font = attributes['main_font']
        if isinstance(main_font, str):
            main_font = getattr(self.r, main_font)

        main_number_label = main_font.render_string(milestone_str)
        main_number_label.thumbnail(attributes['main_area'])

        style = attributes['font_style']
        if style == 'fancy':
            main_number_label = add_transparent_frame(main_number_label, 30)
            shadow_source = add_tint_to_bw_image(main_number_label, tint)
            main_number_label = add_shadow(main_number_label, 6, shadow_source=shadow_source)
            # main_number_label = add_tint_to_bw_image(main_number_label, tint)

        paste_image_masked(image, main_number_label, (mx, my))

        self.put_more_than(image, tint, mx, my, main_number_label.height, desc)

    def put_more_than(self, image, tint, mx, my, label_height, desc):
        if desc.more_than:
            font = self.r.fonts.get_font_bold(44)
            desc_img = draw_text_with_font(self.loc.MORE_THAN, font, tint)
            desc_img = add_transparent_frame(desc_img, 10)
            desc_img = add_shadow(desc_img, 4)
            paste_image_masked(image, desc_img, (mx, my - label_height // 2 + 28), anchor='mb')

    def put_logo(self, image, logo_y=7):
        paste_image_masked(image, self.r.tc_logo_transparent, self.pos_percent(50, logo_y))

    async def prepare(self):
        return await super().prepare()

    @staticmethod
    def attributes_default(r):
        return {
            'main_font': r.custom_font_runic_bw,
            'desc_color': '#fff',
            'desc_stroke': '#1f756a',
            'main_area': (320, 320),
            'font_style': 'fancy',
        }

    DEFAULT_PICTURE_BACKGROUNDS = [
        'nn_wreath_1.png',
        'nn_wreath_2.png',
        'nn_wreath_3.png',
        'nn_wreath_4.png',
    ]

    def choice_background(self):
        if self.force_background:
            return self.force_background
        elif bg := self.ach_desc.preferred_bg:
            if isinstance(bg, str):
                return bg
            else:
                return random.choice(bg)
        else:
            return random.choice(self.DEFAULT_PICTURE_BACKGROUNDS)


def build_achievement_picture_generator(achievement: Achievement, loc: AchievementsLocalizationBase):
    return GenericAchievementPictureGenerator(loc, achievement)
