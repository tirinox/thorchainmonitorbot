from PIL import Image, ImageDraw

from localization.manager import BaseLocalization
from services.dialog.picture.common import BasePictureGenerator
from services.dialog.picture.resources import Resources
from services.lib.draw_utils import TC_WHITE
from services.lib.money import Asset, short_money, short_dollar
from services.lib.utils import async_wrap
from services.notify.types.savers_stats_notify import EventSaverStats


class SaversPictureGenerator(BasePictureGenerator):
    BASE = './data'
    BG_FILE = f'{BASE}/savers_report_bg.png'

    LINE_COLOR = '#41484d'
    COLUMN_COLOR = '#eee'

    def __init__(self, loc: BaseLocalization, event: EventSaverStats):
        super().__init__(loc)
        self.bg = Image.open(self.BG_FILE)
        self.event = event
        self.logos = {}

    FILENAME_PREFIX = 'thorchain_savers'

    async def prepare(self):
        r = Resources()

        for vault in self.event.current_stats.pools:
            logo = await r.logo_downloader.get_or_download_logo_cached(vault.asset)
            self.logos[vault.asset] = logo

    @async_wrap
    def _get_picture_sync(self):
        r = Resources()
        image = self.bg.copy()
        draw = ImageDraw.Draw(image)

        x = 46
        y, dy = 180, 44
        y_start = y
        logo_size = 32

        font_asset = r.fonts.get_font(20)
        font_column = r.fonts.get_font(16)

        draw.text((x, y - dy), 'Asset', fill=self.COLUMN_COLOR, font=font_column)
        draw.text((x + 200, y - dy), 'USD', fill=self.COLUMN_COLOR, font=font_column)
        draw.text((x + 300, y - dy), 'APR', fill=self.COLUMN_COLOR, font=font_column)

        self.event.current_stats.sort_pools(key='total_asset_as_usd', reverse=True)

        def draw_h_line():
            draw.line((x, y - dy // 2, self.WIDTH - x, y - dy // 2), fill=self.LINE_COLOR, width=2)

        for vault in self.event.current_stats.pools:
            logo = self.logos.get(vault.asset)
            if logo:
                logo = logo.copy()
                logo.thumbnail((logo_size, logo_size))
                image.paste(logo, (x, y - logo_size // 2), logo)

            a = Asset.from_string(vault.asset)
            # draw.text((x + 30, y), f'{a.name}', fill=TC_WHITE, font=font_asset, anchor='lm')

            draw.text((x + 42, y),
                      f"{short_money(vault.total_asset_saved)} {a.name}",
                      fill=TC_WHITE, font=font_asset, anchor='lm')

            draw.text((x + 200, y),
                      f"{short_dollar(vault.total_asset_as_usd)}",
                      fill=TC_WHITE, font=font_asset, anchor='lm')

            draw.text((x + 300, y),
                      f"{short_money(vault.apr)}%",
                      fill=TC_WHITE, font=font_asset, anchor='lm')

            draw_h_line()

            y += dy

        draw_h_line()

        v_lines_x = [190, 285]

        for v_line_x in v_lines_x:
            draw.line((x + v_line_x, y_start - dy // 2, x + v_line_x, y - dy // 2), fill=self.LINE_COLOR, width=1)

        # todo
        return image
