from PIL import Image, ImageDraw

from localization.eng_base import BaseLocalization
from services.dialog.picture.common import BasePictureGenerator
from services.dialog.picture.resources import Resources
from services.lib.draw_utils import result_color
from services.lib.money import calc_percent_change, pretty_money, Asset, short_money
from services.lib.utils import async_wrap
from services.models.pool_info import PoolMapPair


class PoolPictureGenerator(BasePictureGenerator):
    BASE = './data'
    BG_FILE = f'{BASE}/pools_bg.png'

    N_POOLS = 7

    def __init__(self, loc: BaseLocalization, event: PoolMapPair):
        super().__init__(loc)
        self.bg = Image.open(self.BG_FILE)
        self.event = event
        self.logos = {}
        self.r = Resources()

    FILENAME_PREFIX = 'thorchain_pools'

    async def prepare(self):
        r = Resources()

        for vault in self.event.all_assets:
            logo = await r.logo_downloader.get_or_download_logo_cached(vault)
            self.logos[vault] = logo

    def draw_one_number(self, draw, image, name, row, col, value, percent_diff, prefix='', suffix='', color='#fff'):
        value_font = self.r.fonts.get_font_bold(50)
        name_font = self.r.fonts.get_font_bold(50)
        number_font = self.r.fonts.get_font(38)
        percent_font = self.r.fonts.get_font(28)

        x = [110, 749, 1392][col]
        y = 300 + 124 * row
        logo_size = 50

        # row number
        draw.text((x, y), f'{row}.', fill='#999', font=number_font, anchor='lt')

        # logo
        a = Asset(name.asset)
        logo = self.logos.get(name.asset)
        if logo:
            logo = logo.copy()
            logo.thumbnail((logo_size, logo_size))
            logo_x, logo_y = x + 49, y - logo_size // 2 + 12
            image.paste(logo, (logo_x, logo_y), logo)

            ambiguous_name = a.gas_asset_from_chain(a.chain) != a
            if ambiguous_name:
                gas_asset = a.gas_asset_from_chain(a.chain)
                gas_logo = self.logos.get(str(gas_asset))
                if gas_logo:
                    gas_logo = gas_logo.copy()
                    gas_logo.thumbnail((logo_size // 2, logo_size // 2))
                    image.paste(gas_logo, (logo_x - 4, logo_y - 4), gas_logo)

        # asset
        name = a.name
        draw.text((x + 120, y - 8), name, fill=color, font=name_font, anchor='lt')

        # value
        has_change_field = percent_diff and value and abs(percent_diff) > 0.1

        value = '-' if value is None else short_money(value)
        value_y = y - 12 if has_change_field else y - 12
        draw.text((x + 540, value_y), f'{prefix}{value}{suffix}', fill='#dee', font=value_font, anchor='rt')

        # percent change
        if has_change_field:
            color = result_color(percent_diff)
            draw.text((x + 540, y + 41), pretty_money(percent_diff, postfix='%', signed=True),
                      fill=color, font=percent_font, anchor='rt')

        # bottom line
        if row != self.N_POOLS:
            line_y = y + 73
            draw.line((x, line_y, x + 540, line_y), fill='#577', width=2)

    @async_wrap
    def _get_picture_sync(self):
        # prepare data
        r, loc, e = self.r, self.loc, self.event

        # prepare painting stuff
        image = self.bg.copy()
        draw = ImageDraw.Draw(image)

        # header = loc.top_pools()
        header = "TOP POOLS"
        draw.text((830, 106), header,
                  fill='#fff', font=r.fonts.get_font_bold(80),
                  anchor='lm')

        sub_header_font = r.fonts.get_font(60)
        sub_header_color = '#bbb'
        draw.text((240, 290), "BEST APR", fill=sub_header_color, font=sub_header_font, anchor='lt')
        draw.text((850, 290), "TOP VOLUME", fill=sub_header_color, font=sub_header_font, anchor='lt')
        draw.text((1530, 290), "DEEPEST", fill=sub_header_color, font=sub_header_font, anchor='lt')

        # numbers
        for column, attr_name in enumerate([PoolMapPair.BY_APR, PoolMapPair.BY_VOLUME_24h, PoolMapPair.BY_DEPTH]):
            top_pools = e.get_top_pools(attr_name, n=self.N_POOLS)
            for i, pool in enumerate(top_pools, start=1):
                v = e.get_value(pool.asset, attr_name)
                p = e.get_difference_percent(pool.asset, attr_name)
                prefix, suffix = '', ''
                if attr_name == PoolMapPair.BY_APR:
                    suffix = '%'
                elif attr_name == PoolMapPair.BY_VOLUME_24h:
                    prefix = '$'
                else:
                    prefix = '$'
                self.draw_one_number(draw, image, pool, i, column, v, p, prefix, suffix)

        # note
        note_text = "1) Percentage changes are shown for a period of 24 hours"
        note_font = r.fonts.get_font(30)
        draw.text((self.bg.width - 16, self.bg.height - 16), note_text, fill='#999', font=note_font, anchor='rb')

        return image
