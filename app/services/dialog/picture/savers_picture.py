from PIL import Image, ImageDraw

from localization.manager import BaseLocalization
from services.dialog.picture.common import BasePictureGenerator
from services.dialog.picture.resources import Resources
from services.lib.draw_utils import TC_WHITE, result_color, rect_progress_bar
from services.lib.money import short_money, short_dollar
from services.lib.utils import async_wrap
from services.models.asset import Asset, is_ambiguous_asset
from services.models.savers import SaverVault, AlertSaverStats


class SaversPictureGenerator(BasePictureGenerator):
    BASE = './data'
    BG_FILE = f'{BASE}/savers_report_bg.png'

    LINE_COLOR = '#41484d'
    COLUMN_COLOR = '#eee'

    WIDTH = 2048
    HEIGHT = 1200

    def __init__(self, loc: BaseLocalization, event: AlertSaverStats):
        super().__init__(loc)
        self.bg = Image.open(self.BG_FILE)
        self.event = event
        self.logos = {}

    FILENAME_PREFIX = 'thorchain_savers'

    async def prepare(self):
        r = Resources()

        for vault in self.event.current_stats.vaults:
            logo = await r.logo_downloader.get_or_download_logo_cached(vault.asset)
            self.logos[vault.asset] = logo

    @async_wrap
    def _get_picture_sync(self):
        # prepare data
        cur_data = self.event.current_stats
        prev_data = self.event.previous_stats

        pool_map = self.event.price_holder.pool_info_map
        usd_per_rune = self.event.price_holder.usd_per_rune

        cur_data.sort_vaults(key='total_asset_saved_usd', reverse=True)

        # prepare painting stuff
        r = Resources()
        image = self.bg.copy()
        draw = ImageDraw.Draw(image)

        # title
        draw.text((388 * 2, 56 * 2),
                  self.loc.TEXT_PIC_SAVERS_VAULTS,
                  fill=TC_WHITE, anchor='lm',
                  font=r.fonts.get_font(64))

        # key metrics:

        key_metrics_y = 215
        n_key_metrics = 5

        def key_metric_xy(i, dx=0, dy=0):
            return dx + self.WIDTH / (n_key_metrics + 1) * i, dy + key_metrics_y

        font_asset_bold = r.fonts.get_font(40, r.fonts.FONT_BOLD)
        font_asset_regular = r.fonts.get_font(40)
        font_column = r.fonts.get_font(36)

        key_metrics_font = r.fonts.get_font(39)
        key_metrics_v_font = r.fonts.get_font(48, r.fonts.FONT_BOLD)
        changed_font = r.fonts.get_font(27)

        def extract_value(data, key, args):
            current_value = getattr(data, key)
            return current_value(*args) if callable(current_value) else current_value

        def draw_key_metric(index, name, key, formatter, extra_args=None):
            current_value = extract_value(cur_data, key, extra_args)

            draw.text(key_metric_xy(index), name, font=key_metrics_font, fill='#aaa', anchor='mm')
            draw.text(key_metric_xy(index, dy=46),
                      formatter(current_value),
                      font=key_metrics_v_font, fill=TC_WHITE, anchor='mm')

            if prev_data:
                prev_value = extract_value(prev_data, key, extra_args)
                delta = current_value - prev_value
                if abs(delta) > 0.001:
                    draw.text(key_metric_xy(index, dy=92),
                              formatter(delta, signed=True),
                              font=changed_font,
                              fill=result_color(delta),
                              anchor='mm')

        draw_key_metric(1, self.loc.TEXT_PIC_SAVERS_TOTAL_SAVERS, 'total_unique_savers', short_money)
        draw_key_metric(2, self.loc.TEXT_PIC_SAVERS_TOTAL_SAVED_VALUE, 'total_usd_saved', short_dollar)
        draw_key_metric(3, self.loc.TEXT_PIC_SAVERS_TOTAL_EARNED, 'total_rune_earned',
                        formatter=lambda x, **_: short_dollar(x * usd_per_rune, signed=True))
        draw_key_metric(4, self.loc.TEXT_PIC_SAVERS_APR_MEAN, 'average_apr',
                        formatter=lambda x, **_: f'{x:+.2f}%')
        draw_key_metric(5, self.loc.TEXT_PIC_SAVERS_TOTAL_FILLED, 'overall_fill_cap_percent',
                        formatter=lambda x, **_: short_money(x, postfix='%'),
                        extra_args=[pool_map])

        # table:
        table_x = 46 * 2
        y, dy = 460, 84
        y_start = y
        logo_size = 32 * 2

        asset_x = 42 * 2 + table_x
        dollar_x = 200 * 2 + table_x
        apr_x = 300 * 2 + table_x
        savers_n_x = 400 * 2 + table_x
        filled_x = 480 * 2 + table_x
        earned_x = 680 * 2 + table_x

        column_y = y_start - 60

        draw.text((asset_x, column_y), self.loc.TEXT_PIC_SAVERS_ASSET,
                  fill=self.COLUMN_COLOR, font=font_column, anchor='lb')
        draw.text((dollar_x, column_y), self.loc.TEXT_PIC_SAVERS_USD,
                  fill=self.COLUMN_COLOR, font=font_column, anchor='lb')
        draw.text((apr_x, column_y), self.loc.TEXT_PIC_SAVERS_APR,
                  fill=self.COLUMN_COLOR, font=font_column, anchor='lb')
        draw.text((savers_n_x, column_y), self.loc.TEXT_PIC_SAVERS,
                  fill=self.COLUMN_COLOR, font=font_column, anchor='lb')
        draw.text((filled_x, column_y), self.loc.TEXT_PIC_SAVERS_FILLED,
                  fill=self.COLUMN_COLOR, font=font_column, anchor='lb')
        draw.text((earned_x, column_y), self.loc.TEXT_PIC_SAVERS_EARNED,
                  fill=self.COLUMN_COLOR, font=font_column, anchor='lb')

        h_line_width, v_line_width = 1, 1
        fill_pb_width = 200

        def draw_h_line():
            draw.line((table_x, y - dy // 2, self.WIDTH - table_x, y - dy // 2), fill=self.LINE_COLOR,
                      width=h_line_width)

        prev_vaults = {p.asset: p for p in prev_data.vaults} if prev_data else {}

        def draw_metric(_x, _y, key, _vault, formatter, tolerance, **kwargs):
            _prev_vault: SaverVault = prev_vaults.get(_vault.asset)
            v = getattr(_vault, key)
            _delta = (v - getattr(_prev_vault, key)) if _prev_vault else None

            significant = _delta and (abs(_delta) > abs(v) * tolerance * 0.01)  # if change > tolerance %

            _dy = -18 if significant else 0
            font = font_asset_bold if kwargs.get('bold', True) else font_asset_regular
            draw.text((_x, _y + _dy),
                      formatter(v, **kwargs),
                      fill=TC_WHITE, font=font, anchor='lm')

            if significant:
                draw.text((_x, _y + 23),
                          formatter(_delta, signed=True, **kwargs),
                          fill=result_color(_delta), font=changed_font, anchor='lm')

        all_asset_names = [v.asset for v in cur_data.vaults]
        for vault in cur_data.vaults:
            logo = self.logos.get(vault.asset)
            if logo:
                logo = logo.copy()
                logo.thumbnail((logo_size, logo_size))
                image.paste(logo, (table_x, y - logo_size // 2), logo)

            a = Asset.from_string(vault.asset)
            # if a.name in ambiguous_names:
            if is_ambiguous_asset(str(a), all_asset_names):
                gas_asset = a.gas_asset_from_chain(a.chain)
                gas_logo = self.logos.get(str(gas_asset))
                if gas_logo:
                    gas_logo = gas_logo.copy()
                    gas_logo.thumbnail((logo_size // 2, logo_size // 2))
                    image.paste(gas_logo, (table_x - 4, y - logo_size // 2 - 4), gas_logo)

            draw_metric(asset_x, y, 'total_asset_saved', vault,
                        formatter=short_money, tolerance=0.1,
                        postfix=f' {a.name}')

            draw_metric(dollar_x, y, 'total_asset_saved_usd', vault,
                        formatter=short_dollar, tolerance=0.5)

            draw_metric(apr_x, y, 'apr', vault,
                        formatter=short_money, tolerance=1.0,
                        postfix='%')

            draw_metric(savers_n_x, y, 'number_of_savers', vault,
                        formatter=short_money, tolerance=0.0,
                        integer=True)

            draw.text((filled_x + fill_pb_width + 34, y - 4),
                      f"{short_money(vault.percent_of_cap_filled, integer=True)}%",
                      fill=TC_WHITE, font=font_asset_bold, anchor='lm')

            rect_progress_bar(draw, vault.percent_of_cap_filled / 100.0,
                              ((filled_x, y - 14), (fill_pb_width, 28)), line_width=2, gap=2)

            asset_earned = vault.calc_asset_earned(pool_map)
            usd_earned = vault.runes_earned * usd_per_rune
            draw.text((earned_x, y),
                      f"{short_money(asset_earned)} {a.name} {self.loc.TEXT_PIC_SAVERS_OR} "
                      f"{short_dollar(usd_earned)}",
                      fill=TC_WHITE, font=font_asset_regular, anchor='lm')

            draw_h_line()

            y += dy

        draw_h_line()

        y_v_line_start = y_start - dy // 2
        y_end = y - dy // 2
        for v_line_x in [dollar_x, apr_x, savers_n_x, filled_x, earned_x]:
            x = v_line_x - 34
            draw.line((x, y_v_line_start, x, y_end), fill=self.LINE_COLOR, width=v_line_width)

        return image
