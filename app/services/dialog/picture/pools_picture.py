from PIL import Image, ImageDraw

from localization.eng_base import BaseLocalization
from services.dialog.picture.common import BasePictureGenerator
from services.dialog.picture.resources import Resources
from services.lib.draw_utils import result_color, TC_LIGHTNING_BLUE
from services.lib.money import pretty_money, short_money, short_dollar
from services.lib.utils import async_wrap
from services.models.asset import Asset
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
        self.chain_logos = {}
        self.r = Resources()

    FILENAME_PREFIX = 'thorchain_pools'

    async def prepare(self):
        r = Resources()

        for vault in self.event.all_assets:
            logo = await r.logo_downloader.get_or_download_logo_cached(vault)
            self.logos[vault] = logo

            chain = Asset(vault).chain
            if chain:
                chain_logo = await r.logo_downloader.get_logo_for_chain(chain)
                self.chain_logos[chain] = chain_logo

    def draw_one_number(self, draw, image, name, row, col, value, percent_diff, prefix='', suffix='',
                        total_value=None, attr_value_accum=0.0):
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
                # gas_asset = a.gas_asset_from_chain(a.chain)
                # gas_logo = self.logos.get(str(gas_asset))
                gas_logo = self.chain_logos.get(a.chain)
                if gas_logo:
                    gas_logo = gas_logo.copy()
                    gas_logo.thumbnail((logo_size // 2, logo_size // 2))
                    image.paste(gas_logo, (logo_x - 4, logo_y - 4), gas_logo)

        # asset
        name = a.name
        draw.text((x + 120, y - 8), name, fill='#fff', font=name_font, anchor='lt')

        # value
        has_change_field = percent_diff and value and abs(percent_diff) > 0.1

        value_str = '-' if value is None else short_money(value)
        value_y = y - 12 if has_change_field else y - 12
        draw.text((x + 540, value_y), f'{prefix}{value_str}{suffix}', fill='#dee', font=value_font, anchor='rt')

        # percent change
        if has_change_field:
            color = result_color(percent_diff)
            draw.text((x + 540, y + 41), pretty_money(percent_diff, postfix='%', signed=True),
                      fill=color, font=percent_font, anchor='rt')

        # bottom line
        line_width, line_y = 540, y + 76
        last_line = row == self.N_POOLS
        if not last_line:
            draw.line((x, line_y, x + line_width, line_y), fill='#577', width=2)

        # share of total
        if total_value and not last_line:
            x_offset = attr_value_accum / total_value * line_width if total_value else 0
            partial_width = value / total_value * line_width if total_value else 0

            draw.line((x + x_offset, line_y, x + x_offset + partial_width, line_y), fill=TC_LIGHTNING_BLUE, width=4)
            # small vertical notches to left and right of the span
            draw.line((x + x_offset, line_y - 4, x + x_offset, line_y + 4), fill=TC_LIGHTNING_BLUE, width=1)
            draw.line((x + x_offset + partial_width, line_y - 4, x + x_offset + partial_width, line_y + 4),
                      fill=TC_LIGHTNING_BLUE, width=1)


    @async_wrap
    def _get_picture_sync(self):
        # prepare data
        r, loc, e = self.r, self.loc, self.event

        # prepare painting stuff
        image = self.bg.copy()
        draw = ImageDraw.Draw(image)

        # header = loc.top_pools()
        header = loc.TEXT_BP_HEADER
        draw.text((830, 106), header,
                  fill='#fff', font=r.fonts.get_font_bold(80),
                  anchor='lm')

        sub_header_font = r.fonts.get_font(60)
        sub_header_color = '#bbb'
        draw.text((240, 290), loc.TEXT_BP_BEST_APR_TITLE, fill=sub_header_color, font=sub_header_font, anchor='lt')
        draw.text((850, 290), loc.TEXT_BP_HIGH_VOLUME_TITLE, fill=sub_header_color, font=sub_header_font, anchor='lt')
        draw.text((1530, 290), loc.TEXT_BP_DEEPEST_TITLE, fill=sub_header_color, font=sub_header_font, anchor='lt')

        # numbers
        for column, attr_name in enumerate([PoolMapPair.BY_APR, PoolMapPair.BY_VOLUME_24h, PoolMapPair.BY_DEPTH]):
            top_pools = e.get_top_pools(attr_name, n=self.N_POOLS)
            total_value = e.total_liquidity() if attr_name == PoolMapPair.BY_DEPTH else e.total_volume_24h()
            attr_value_accum = 0.0
            for i, pool in enumerate(top_pools, start=1):
                v = e.get_value(pool.asset, attr_name)
                p = e.get_difference_percent(pool.asset, attr_name)
                prefix, suffix = '', ''
                if attr_name == PoolMapPair.BY_APR:
                    suffix = '%'
                    total_value = None
                elif attr_name == PoolMapPair.BY_VOLUME_24h:
                    prefix = '$'
                else:
                    prefix = '$'
                self.draw_one_number(draw, image, pool, i, column, v, p, prefix, suffix, total_value, attr_value_accum)
                attr_value_accum += v

        bottom_value_y = self.bg.height - 192
        bottom_text_y = self.bg.height - 134
        bottom_value_font = r.fonts.get_font_bold(80)
        bottom_text_font = r.fonts.get_font(48)

        # total pools
        x = 240
        total_pools = e.number_of_active_pools
        draw.text((x, bottom_value_y), str(total_pools), fill='#eee', font=bottom_value_font, anchor='lm')
        draw.text((x, bottom_text_y), loc.TEXT_BP_ACTIVE_POOLS, fill='#aaa', font=bottom_text_font, anchor='lt')

        # total volume
        x = 870
        total_volume = short_dollar(e.total_volume_24h())
        draw.text((x, bottom_value_y), total_volume, fill='#eee', font=bottom_value_font, anchor='lm')
        draw.text((x, bottom_text_y), loc.TEXT_BP_24H_VOLUME, fill='#aaa', font=bottom_text_font, anchor='lt')

        # total liquidity
        x = 1512
        total_liquidity = short_dollar(e.total_liquidity())
        draw.text((x, bottom_value_y), total_liquidity, fill='#eee', font=bottom_value_font, anchor='lm')
        draw.text((x, bottom_text_y), loc.TEXT_BP_TOTAL_LIQ, fill='#aaa', font=bottom_text_font, anchor='lt')

        return image
