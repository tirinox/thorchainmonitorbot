from PIL import Image, ImageDraw

from localization.manager import BaseLocalization
from services.dialog.picture.common import BasePictureGenerator
from services.dialog.picture.resources import Resources
from services.lib.draw_utils import TC_WHITE, line_progress_bar
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

        # title
        draw.text((388, 69),
                  self.loc.TEXT_PIC_SAVERS_VAULTS,
                  fill=TC_WHITE, anchor='lb',
                  font=r.fonts.get_font(32))

        table_x = 46
        y, dy = 180, 44
        y_start = y
        logo_size = 32

        asset_x = 42 + table_x
        dollar_x = 200 + table_x
        apr_x = 300 + table_x
        savers_n_x = 400 + table_x
        filled_x = 500 + table_x

        font_asset = r.fonts.get_font(20)
        font_column = r.fonts.get_font(16)

        column_y = y_start - 30

        draw.text((asset_x, column_y), 'Asset', fill=self.COLUMN_COLOR, font=font_column, anchor='lb')
        draw.text((dollar_x, column_y), 'USD', fill=self.COLUMN_COLOR, font=font_column, anchor='lb')
        draw.text((apr_x, column_y), 'APR', fill=self.COLUMN_COLOR, font=font_column, anchor='lb')
        draw.text((savers_n_x, column_y), 'Savers', fill=self.COLUMN_COLOR, font=font_column, anchor='lb')
        draw.text((filled_x, column_y), 'Savers filled', fill=self.COLUMN_COLOR, font=font_column, anchor='lb')

        self.event.current_stats.sort_pools(key='total_asset_as_usd', reverse=True)

        h_line_width, v_line_width = 1, 2

        def draw_h_line():
            draw.line((table_x, y - dy // 2, self.WIDTH - table_x, y - dy // 2), fill=self.LINE_COLOR,
                      width=h_line_width)

        for vault in self.event.current_stats.pools:
            logo = self.logos.get(vault.asset)
            if logo:
                logo = logo.copy()
                logo.thumbnail((logo_size, logo_size))
                image.paste(logo, (table_x, y - logo_size // 2), logo)

            a = Asset.from_string(vault.asset)
            # draw.text((x + 30, y), f'{a.name}', fill=TC_WHITE, font=font_asset, anchor='lm')

            draw.text((asset_x, y),
                      f"{short_money(vault.total_asset_saved)} {a.name}",
                      fill=TC_WHITE, font=font_asset, anchor='lm')

            draw.text((dollar_x, y),
                      f"{short_dollar(vault.total_asset_as_usd)}",
                      fill=TC_WHITE, font=font_asset, anchor='lm')

            draw.text((apr_x, y),
                      f"{short_money(vault.apr)}%",
                      fill=TC_WHITE, font=font_asset, anchor='lm')

            draw.text((savers_n_x, y),
                      f"{short_money(vault.number_of_savers, integer=True)}",
                      fill=TC_WHITE, font=font_asset, anchor='lm')

            draw.text((filled_x, y),
                      f"{short_money(vault.percent_of_cap_filled, integer=True)}%",
                      fill=TC_WHITE, font=font_asset, anchor='lm')

            line_progress_bar(draw, vault.percent_of_cap_filled / 100.0,
                              ((filled_x + 72, y - 7), (100, 14)), line_width=2, gap=2)

            draw_h_line()

            y += dy

        draw_h_line()

        y_v_line_start = y_start - dy // 2
        y_end = y - dy // 2
        for v_line_x in [dollar_x, apr_x, savers_n_x, filled_x]:
            x = v_line_x - 17
            draw.line((x, y_v_line_start, x, y_end), fill=self.LINE_COLOR, width=v_line_width)

        # todo
        return image
