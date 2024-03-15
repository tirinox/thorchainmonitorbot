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
        self.btc_logo = None
        self.eth_logo = None
        self.usdt_logo = self.usdc_logo = self.busd_logo = None

    FILENAME_PREFIX = 'thorchain_pools'

    async def prepare(self):
        r = Resources()

        for vault in self.event.all_assets:
            logo = await r.logo_downloader.get_or_download_logo_cached(vault)
            self.logos[vault] = logo

    def draw_one_number(self, draw, image, name, row, col, value, prev_value, prefix='', suffix='', color='#fff'):
        value_font = self.r.fonts.get_font(70)
        name_font = self.r.fonts.get_font_bold(50)
        number_font = self.r.fonts.get_font(46)

        x = [66, 749, 1419][col]
        y = 308 + 124 * row
        logo_size = 50

        # row number
        draw.text((x, y), f'{row}.', fill=color, font=number_font, anchor='lt')

        # logo
        a = Asset(name.asset)
        logo = self.logos.get(name.asset)
        if logo:
            logo = logo.copy()
            logo.thumbnail((logo_size, logo_size))
            logo_x, logo_y = x + 49, y - logo_size // 2 + 15
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
        draw.text((x + 120, y), name, fill=color, font=name_font, anchor='lt')

        # value
        value = '-' if value is None else short_money(value)
        draw.text((x + 540, y - 20), f'{prefix}{value}{suffix}', fill='#dee', font=value_font, anchor='rt')

        # percent change
        if prev_value and value:
            percent_change = calc_percent_change(prev_value, value)
            if percent_change is not None:
                color = result_color(percent_change)
                draw.text((x, y + 40), f'{percent_change:+.1f}%', fill=color, font=value_font, anchor='lt')

        # bottom line
        if row != self.N_POOLS:
            line_y = y + 70
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
        draw.text((210, 290), "BEST APR", fill='#fff', font=sub_header_font, anchor='lt')
        draw.text((850, 290), "TOP VOLUME", fill='#fff', font=sub_header_font, anchor='lt')
        draw.text((1570, 290), "DEEPEST", fill='#fff', font=sub_header_font, anchor='lt')

        # vertical lines
        # xs = 2048 // 3
        # y1, y2 = 240, 1400
        # draw.line((xs, y1, xs, y2), fill='#fff', width=2)
        # xs *= 2
        # draw.line((xs, y1, xs, y2), fill='#fff', width=2)

        # numbers
        for column, attr_name in enumerate([PoolMapPair.BY_APY, PoolMapPair.BY_VOLUME_24h, PoolMapPair.BY_DEPTH]):
            top_pools = e.get_top_pools(attr_name, n=self.N_POOLS)
            print(top_pools)
            print('-----')
            for i, pool in enumerate(top_pools, start=1):
                v = e.get_value(pool.asset, attr_name)
                p = e.get_difference_percent(pool.asset, attr_name)
                prefix, suffix = '', ''
                if attr_name == PoolMapPair.BY_APY:
                    p = p or 0.0
                    p *= 100.0
                    suffix = '%'
                elif attr_name == PoolMapPair.BY_VOLUME_24h:
                    prefix = '$'
                else:
                    prefix = '$'
                self.draw_one_number(draw, image, pool, i, column, v, p, prefix, suffix)

        return image
