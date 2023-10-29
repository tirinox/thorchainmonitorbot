import abc
import datetime
import os.path
import random

from PIL import Image, ImageDraw

from localization.achievements.ach_eng import AchievementsLocalizationBase
from services.dialog.picture.common import BasePictureGenerator
from services.dialog.picture.resources import Resources
from services.jobs.achievement.ach_list import Achievement, A
from services.lib.date_utils import today_str
from services.lib.draw_utils import pos_percent, paste_image_masked, measure_font_to_fit_in_box, convert_indexed_png, \
    add_shadow, add_transparent_frame, add_tint_to_bw_image, adjust_brightness, \
    extract_characteristic_color, draw_text_with_font
from services.lib.utils import async_wrap


class GenericAchievementPictureGenerator(BasePictureGenerator, abc.ABC):
    BASE = './data/achievement'
    WIDTH = 1024
    HEIGHT = 1024

    @abc.abstractmethod
    def choice_background(self):
        ...

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
        # self.more_or_equals = '≥'
        self.more_or_equals = ''

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
        _desc, ago, desc_text, emoji, milestone_str, prev_milestone_str, value_str = self.loc.prepare_achievement_data(
            self.ach,
            newlines=True,
        )

        bg = self.load_background_picture()

        # get dominant color of the background
        tint = self.get_tint(bg)
        draw = ImageDraw.Draw(bg)
        attributes = self.custom_attributes(self.r)  # for this kind of achievement

        self.put_logo(bg)
        self.put_main_number(bg, draw, attributes, milestone_str, tint)
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

    def put_main_number(self, image, draw, attributes, milestone_str, tint):
        main_number_y = 46

        mx, my = self.pos_percent(50, main_number_y)
        main_number_label = attributes['main_font'].render_string(milestone_str)
        main_number_label.thumbnail(attributes['main_area'])

        style = attributes['font_style']
        if style == 'fancy':
            main_number_label = add_transparent_frame(main_number_label, 30)
            shadow_source = add_tint_to_bw_image(main_number_label, tint)
            main_number_label = add_shadow(main_number_label, 6, shadow_source=shadow_source)
            # main_number_label = add_tint_to_bw_image(main_number_label, tint)

        # more or equal
        if self.more_or_equals:
            print(main_number_label.height)
            draw.text((mx, my - main_number_label.height // 2),
                      self.more_or_equals, fill=adjust_brightness(tint, 0.7),
                      font=self.r.fonts.get_font_bold(80), anchor='lb')

        paste_image_masked(image, main_number_label, (mx, my))

    LOGO_Y = 6

    def put_logo(self, image):
        paste_image_masked(image, self.r.tc_logo_transparent, self.pos_percent(50, self.LOGO_Y))

    async def prepare(self):
        return await super().prepare()

    def custom_attributes(self, r):
        return {
            'main_font': r.custom_font_runic_bw,
            'desc_color': '#fff',
            'desc_stroke': '#1f756a',
            'main_area': (320, 320),
            'font_style': 'fancy',
        }


class NormalAchievementPictureGenerator(GenericAchievementPictureGenerator):
    PICTURE_BACKGROUNDS = [
        'nn_wreath_1.png',
        'nn_wreath_2.png',
        'nn_wreath_3.png',
        'nn_wreath_4.png',
        'nn_wreath_5.png',
        # 'nn_wreath_experimental_2.png',
    ]

    def choice_background(self):
        if self.force_background:
            return self.force_background
        else:
            return random.choice(self.PICTURE_BACKGROUNDS)


class HappyBirthdayPictureGenerator(GenericAchievementPictureGenerator):
    def choice_background(self):
        return 'nn_wreath_ann_2.png'

    def __init__(self, loc: AchievementsLocalizationBase, a: Achievement):
        super().__init__(loc, a)

    def custom_attributes(self, r):
        return {
            'main_font': r.custom_font_balloon,
            'desc_color': '#f4e18d',
            'desc_stroke': '#954c07',
            'main_area': (320, 320),
            'font_style': 'normal',
        }


def build_achievement_picture_generator(achievement: Achievement, loc: AchievementsLocalizationBase):
    if achievement.key == A.ANNIVERSARY:
        return HappyBirthdayPictureGenerator(loc, achievement)
    elif achievement.key == A.BTC_IN_VAULT:
        return NormalAchievementPictureGenerator(loc, achievement, force_background='nn_wreath_btc_vault.png')
    else:
        return NormalAchievementPictureGenerator(loc, achievement)
