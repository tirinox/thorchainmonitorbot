from PIL import Image, ImageDraw

from localization.manager import BaseLocalization
from services.dialog.picture.common import BasePictureGenerator
from services.dialog.picture.resources import Resources
from services.lib.draw_utils import TC_WHITE, line_progress_bar, result_color
from services.lib.money import Asset, short_money, short_dollar
from services.lib.utils import async_wrap
from services.models.pool_info import PoolInfoMap
from services.notify.types.savers_stats_notify import EventSaverStats


class SaversPictureGenerator(BasePictureGenerator):
    BASE = './data'
    BG_FILE = f'{BASE}/savers_report_bg.png'

    LINE_COLOR = '#41484d'
    COLUMN_COLOR = '#eee'

    def __init__(self, loc: BaseLocalization, event: EventSaverStats, pool_map: PoolInfoMap):
        super().__init__(loc)
        self.bg = Image.open(self.BG_FILE)
        self.event = event
        self.logos = {}
        self.pool_map = pool_map

    FILENAME_PREFIX = 'thorchain_savers'

    async def prepare(self):
        r = Resources()

        for vault in self.event.current_stats.pools:
            logo = await r.logo_downloader.get_or_download_logo_cached(vault.asset)
            self.logos[vault.asset] = logo

    @async_wrap
    def _get_picture_sync(self):
        # prepare
        cur_data = self.event.current_stats
        prev_data = self.event.previous_stats

        r = Resources()
        image = self.bg.copy()
        draw = ImageDraw.Draw(image)

        # title
        draw.text((388, 69),
                  self.loc.TEXT_PIC_SAVERS_VAULTS,
                  fill=TC_WHITE, anchor='lb',
                  font=r.fonts.get_font(32))

        # key metrics:

        key_metrics_y = 115
        n_key_metrics = 5

        def key_metric_xy(i, dx=0, dy=0):
            return dx + self.WIDTH / (n_key_metrics + 1) * i, dy + key_metrics_y

        font_asset_bold = r.fonts.get_font(20, r.fonts.FONT_BOLD)
        font_asset_regular = r.fonts.get_font(20)
        font_column = r.fonts.get_font(18)

        key_metrics_font = r.fonts.get_font(18)
        key_metrics_v_font = r.fonts.get_font(24, r.fonts.FONT_BOLD)
        changed_font = r.fonts.get_font(16)

        def draw_key_metric(index, name, key, formatter, **kwargs):
            current_value = getattr(cur_data, key)

            draw.text(key_metric_xy(index), name, font=key_metrics_font, fill='#aaa', anchor='mm')
            draw.text(key_metric_xy(index, dy=23),
                      formatter(current_value, **kwargs),
                      font=key_metrics_v_font, fill=TC_WHITE, anchor='mm')
            if prev_data:
                delta = current_value - getattr(prev_data, key)
                if delta != 0:
                    draw.text(key_metric_xy(index, dy=46),
                              formatter(delta, signed=True, **kwargs),
                              font=changed_font,
                              fill=result_color(delta),
                              anchor='mm')

        draw_key_metric(1, 'Total Savers', 'total_unique_savers', short_money, integer=True)
        draw_key_metric(2, 'Total Saved Value', 'total_usd_saved', short_dollar)
        draw_key_metric(3, 'Total Earned', 'total_rune_earned',
                        formatter=lambda x, signed=False: short_dollar(x * self.event.usd_per_rune, signed=signed))

        draw_key_metric(4, 'APR Mean', 'average_apr', short_money, postfix='%')
        draw_key_metric(5, 'Total Filled', 'overall_fill_cap_percent', short_money, postfix='%')

        # table:

        table_x = 46
        y, dy = 242, 44
        y_start = y
        logo_size = 32

        asset_x = 42 + table_x
        dollar_x = 200 + table_x
        apr_x = 300 + table_x
        savers_n_x = 400 + table_x
        filled_x = 480 + table_x
        earned_x = 680 + table_x

        column_y = y_start - 30

        draw.text((asset_x, column_y), 'Asset', fill=self.COLUMN_COLOR, font=font_column, anchor='lb')
        draw.text((dollar_x, column_y), 'USD', fill=self.COLUMN_COLOR, font=font_column, anchor='lb')
        draw.text((apr_x, column_y), 'APR', fill=self.COLUMN_COLOR, font=font_column, anchor='lb')
        draw.text((savers_n_x, column_y), 'Savers', fill=self.COLUMN_COLOR, font=font_column, anchor='lb')
        draw.text((filled_x, column_y), 'Savers filled', fill=self.COLUMN_COLOR, font=font_column, anchor='lb')
        draw.text((earned_x, column_y), 'Earned', fill=self.COLUMN_COLOR, font=font_column, anchor='lb')

        cur_data.sort_pools(key='total_asset_as_usd', reverse=True)

        h_line_width, v_line_width = 1, 1
        fill_pb_width = 100

        def draw_h_line():
            draw.line((table_x, y - dy // 2, self.WIDTH - table_x, y - dy // 2), fill=self.LINE_COLOR,
                      width=h_line_width)

        prev_pools = {p.asset: p for p in prev_data.pools} if prev_data else {}

        def get_delta(key, v):
            prev_pool = prev_pools.get(v.asset)
            if prev_pool:
                return getattr(v, key) - getattr(prev_pool, key)

        def draw_metric(_x, _y, key, _vault, formatter, **kwargs):
            _delta = get_delta(key, _vault)

            v = getattr(_vault, key)
            significant = _delta and (abs(_delta) > abs(v) * 0.01)  # if change > 1%

            _dy = -9 if significant else 0

            font = font_asset_bold if kwargs.get('bold', True) else font_asset_regular
            draw.text((_x, _y + _dy),
                      formatter(v, **kwargs),
                      fill=TC_WHITE, font=font, anchor='lm')

            if significant:
                draw.text((_x, _y + 13),
                          formatter(_delta, signed=True, **kwargs),
                          fill=result_color(_delta), font=changed_font, anchor='lm')

        for vault in cur_data.pools:
            logo = self.logos.get(vault.asset)
            if logo:
                logo = logo.copy()
                logo.thumbnail((logo_size, logo_size))
                image.paste(logo, (table_x, y - logo_size // 2), logo)

            a = Asset.from_string(vault.asset)

            #
            # draw.text((asset_x, y),
            #           f"{short_money(vault.total_asset_saved)} {a.name}",
            #           fill=TC_WHITE, font=font_asset, anchor='lm')
            # if delta := get_delta('total_asset_saved', vault):
            #     draw.text((asset_x, y + 10),
            #               f"{short_money(delta)} {a.name}",
            #               fill=result_color(delta), font=changed_font, anchor='lm')
            #
            draw_metric(asset_x, y, 'total_asset_saved', vault,
                        formatter=short_money, postfix=f' {a.name}')

            draw_metric(dollar_x, y, 'total_asset_as_usd', vault,
                        formatter=short_dollar)

            draw_metric(apr_x, y, 'apr', vault,
                        formatter=short_money, postfix='%')

            draw_metric(savers_n_x, y, 'number_of_savers', vault,
                        formatter=short_money, integer=True)

            draw.text((filled_x + fill_pb_width + 20, y),
                      f"{short_money(vault.percent_of_cap_filled, integer=True)}%",
                      fill=TC_WHITE, font=font_asset_bold, anchor='lm')

            line_progress_bar(draw, vault.percent_of_cap_filled / 100.0,
                              ((filled_x, y - 7), (fill_pb_width, 14)), line_width=2, gap=2)

            asset_earned = vault.calc_asset_earned(self.pool_map)
            usd_earned = vault.runes_earned * self.event.usd_per_rune
            draw.text((earned_x, y),
                      f"{short_money(asset_earned)} {a.name} or "
                      f"{short_dollar(usd_earned)}",
                      fill=TC_WHITE, font=font_asset_regular, anchor='lm')

            draw_h_line()

            y += dy

        draw_h_line()

        y_v_line_start = y_start - dy // 2
        y_end = y - dy // 2
        for v_line_x in [dollar_x, apr_x, savers_n_x, filled_x, earned_x]:
            x = v_line_x - 17
            draw.line((x, y_v_line_start, x, y_end), fill=self.LINE_COLOR, width=v_line_width)

        # todo
        return image