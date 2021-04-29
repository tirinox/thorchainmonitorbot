import asyncio
import operator
from collections import defaultdict
from typing import List

from PIL import Image, ImageDraw, ImageFont

from localization import BaseLocalization
from localization.base import RAIDO_GLYPH
from services.dialog.picture.crypto_logo import CryptoLogoDownloader
from services.lib.constants import BNB_RUNE_SYMBOL, is_stable_coin, is_rune, RUNE_SYMBOL
from services.lib.money import pretty_money, short_asset_name, pretty_dollar, format_percent
from services.lib.plot_graph import PlotBarGraph
from services.lib.texts import grouper
from services.lib.utils import Singleton, async_wrap
from services.models.lp_info import LiquidityPoolReport, LPDailyGraphPoint

WIDTH, HEIGHT = 1200, 1600

LINE_COLOR = '#356'
GREEN_COLOR = '#00f2c3'
RED_COLOR = '#e22222'
FORE_COLOR = 'white'
FADE_COLOR = '#cccccc'
CATEGORICAL_PALETTE = [
    '#648FFF', '#785EF0',
    '#DC267F',
    '#FE6100', '#FFB000',
    '#005AB5', '#DC3220'
]
BG_COLOR = '#141a1a'


class Resources(metaclass=Singleton):
    BASE = './data'
    LOGO_WIDTH, LOGO_HEIGHT = 128, 128
    HIDDEN_IMG = f'{BASE}/hidden.png'
    BG_IMG = f'{BASE}/lp_bg.png'

    FONT_BOLD = f'{BASE}/my.ttf'

    def __init__(self) -> None:
        self.hidden_img = Image.open(self.HIDDEN_IMG)
        self.hidden_img.thumbnail((200, 36))

        self.font = ImageFont.truetype(self.FONT_BOLD, 40)
        self.font_head = ImageFont.truetype(self.FONT_BOLD, 48)
        self.font_small = ImageFont.truetype(self.FONT_BOLD, 28)
        self.font_semi = ImageFont.truetype(self.FONT_BOLD, 36)
        self.font_big = ImageFont.truetype(self.FONT_BOLD, 64)
        self.bg_image = Image.open(self.BG_IMG)

        self.logo_downloader = CryptoLogoDownloader(self.BASE)

        self.font_sum_ticks = ImageFont.truetype(self.FONT_BOLD, 24)

    def put_hidden_plate(self, image, position, anchor='left', ey=-3):
        x, y = position
        if anchor == 'right':
            x -= self.hidden_img.width
        elif anchor == 'center':
            x -= self.hidden_img.width // 2
        y -= self.hidden_img.height + ey
        image.paste(self.hidden_img, (x, y), self.hidden_img)


def round_corner(radius, fill, bg):
    """Draw a round corner"""
    corner = Image.new('RGB', (radius, radius), bg)
    draw = ImageDraw.Draw(corner)
    draw.pieslice((0, 0, radius * 2, radius * 2), 180, 270, fill=fill)
    return corner


def pos_percent(x, y, ax=0, ay=0, w=WIDTH, h=HEIGHT):
    return int(x / 100 * w + ax), int(y / 100 * h + ay)


def result_color(v):
    return RED_COLOR if v < 0 else GREEN_COLOR


async def lp_pool_picture(report: LiquidityPoolReport, loc: BaseLocalization, value_hidden=False):
    r = Resources()
    asset = report.pool.asset
    rune_image, asset_image = await asyncio.gather(
        r.logo_downloader.get_or_download_logo_cached(BNB_RUNE_SYMBOL),
        r.logo_downloader.get_or_download_logo_cached(asset)
    )
    return await sync_lp_pool_picture(report, loc, rune_image, asset_image, value_hidden)


def hor_line(draw, y, width=2, w=WIDTH, h=HEIGHT):
    draw.line((pos_percent(0, y, w=w, h=h), pos_percent(100, y, w=w, h=h)), fill=LINE_COLOR, width=width)


@async_wrap
def sync_lp_pool_picture(report: LiquidityPoolReport, loc: BaseLocalization, rune_image, asset_image, value_hidden):
    asset = report.pool.asset

    r = Resources()

    image = r.bg_image.copy()
    draw = ImageDraw.Draw(image)

    left, center, right = 30, 50, 70
    head_y = 16
    dy = 4.5
    logo_y = 82
    start_y = head_y + dy

    # HEADER
    draw.text(pos_percent(center, head_y), loc.LP_PIC_POOL, font=r.font_head, fill=FADE_COLOR, anchor='ms')
    draw.text(pos_percent(left, head_y), loc.LP_PIC_RUNE, font=r.font_head, fill=FORE_COLOR, anchor='rs')
    draw.text(pos_percent(right, head_y), short_asset_name(asset), font=r.font_head, fill=FORE_COLOR, anchor='ls')

    # ------------------------------------------------------------------------------------------------
    # line1_y = 11
    # draw.line((pos_percent(0, line1_y), pos_percent(100, line1_y)), fill=LINE_COLOR, width=2)
    # ------------------------------------------------------------------------------------------------

    # ADDED
    draw.text(pos_percent(center, start_y), loc.LP_PIC_ADDED, font=r.font, fill=FADE_COLOR, anchor='ms')
    if value_hidden:
        r.put_hidden_plate(image, pos_percent(left, start_y), anchor='right')
        r.put_hidden_plate(image, pos_percent(right, start_y), anchor='left')
    else:
        draw.text(pos_percent(left, start_y), f'{pretty_money(report.liq.rune_stake)} {RAIDO_GLYPH}', font=r.font,
                  fill=FORE_COLOR,
                  anchor='rs')
        draw.text(pos_percent(right, start_y), f'{pretty_money(report.liq.asset_stake)}', font=r.font, fill=FORE_COLOR,
                  anchor='ls')
    start_y += dy

    # WITHDRAWN
    draw.text(pos_percent(center, start_y), loc.LP_PIC_WITHDRAWN, font=r.font, fill=FADE_COLOR, anchor='ms')
    if value_hidden:
        r.put_hidden_plate(image, pos_percent(left, start_y), anchor='right')
        r.put_hidden_plate(image, pos_percent(right, start_y), anchor='left')
    else:
        draw.text(pos_percent(left, start_y), f'{pretty_money(report.liq.rune_withdrawn)} {RAIDO_GLYPH}', font=r.font,
                  fill=FORE_COLOR,
                  anchor='rs')
        draw.text(pos_percent(right, start_y), f'{pretty_money(report.liq.asset_withdrawn)}', font=r.font,
                  fill=FORE_COLOR,
                  anchor='ls')
    start_y += dy

    # REDEEMABLE
    draw.text(pos_percent(center, start_y), loc.LP_PIC_REDEEM, font=r.font, fill=FADE_COLOR, anchor='ms')
    redeem_rune, redeem_asset = report.redeemable_rune_asset
    if value_hidden:
        r.put_hidden_plate(image, pos_percent(left, start_y), anchor='right')
        r.put_hidden_plate(image, pos_percent(right, start_y), anchor='left')
    else:
        draw.text(pos_percent(left, start_y), f'{pretty_money(redeem_rune)} {RAIDO_GLYPH}', font=r.font,
                  fill=FORE_COLOR,
                  anchor='rs')
        draw.text(pos_percent(right, start_y), f'{pretty_money(redeem_asset)}', font=r.font, fill=FORE_COLOR,
                  anchor='ls')
    start_y += dy

    # GAIN LOSS
    draw.text(pos_percent(center, start_y), loc.LP_PIC_GAIN_LOSS, font=r.font, fill=FADE_COLOR, anchor='ms')
    gl_rune, gl_rune_per, gl_asset, gl_asset_per = report.gain_loss_raw
    if not value_hidden:
        draw.text(pos_percent(left, start_y), f'{pretty_money(gl_rune, signed=True)} {RAIDO_GLYPH}', font=r.font,
                  fill=result_color(gl_rune),
                  anchor='rs')
        draw.text(pos_percent(right, start_y), f'{pretty_money(gl_asset, signed=True)}', font=r.font,
                  fill=result_color(gl_asset),
                  anchor='ls')
    start_y += 4

    # GAIN LOSS PERCENT
    gl_usd, gl_usd_p = report.gain_loss(report.USD)

    draw.text(pos_percent(center, start_y), f'{pretty_money(gl_usd_p, signed=True)}% {loc.LP_PIC_IN_USD}',
              font=r.font_head if value_hidden else r.font,
              fill=result_color(gl_usd_p),
              anchor='ms')

    ey = -2 if value_hidden else 0
    draw.text(pos_percent(left, start_y + ey), f'{pretty_money(gl_rune_per, signed=True)}%',
              font=r.font_head if value_hidden else r.font,
              fill=result_color(gl_rune_per),
              anchor='rs')
    draw.text(pos_percent(right, start_y + ey), f'{pretty_money(gl_asset_per, signed=True)}%',
              font=r.font_head if value_hidden else r.font,
              fill=result_color(gl_asset_per),
              anchor='ls')
    start_y += 3

    # ------------------------------------------------------------------------------------------------
    hor_line(draw, start_y)
    # ------------------------------------------------------------------------------------------------
    start_y += 5

    # VALUE
    table_x = 30
    rows_y = [start_y + 4 + r * 4 for r in range(6)]

    if is_stable_coin(asset):
        columns = (report.RUNE, report.ASSET)
        columns_x = [50 + c * 25 for c in range(2)]
    else:
        columns = (report.RUNE, report.ASSET, report.USD)
        columns_x = [44 + c * 19 for c in range(3)]
        draw.text(pos_percent(columns_x[2], start_y), 'USD', font=r.font, fill=FADE_COLOR, anchor='ms')

    draw.text(pos_percent(columns_x[0], start_y), loc.LP_PIC_R_RUNE, font=r.font, fill=FADE_COLOR, anchor='ms')
    draw.text(pos_percent(columns_x[1], start_y), short_asset_name(asset), font=r.font, fill=FADE_COLOR, anchor='ms')

    for x, column in zip(columns_x, columns):
        gl, _ = report.gain_loss(column)

        fee_value = report.fee_value(column)
        current = report.current_value(column)

        if not value_hidden:
            added = report.added_value(column)
            withdrawn = report.withdrawn_value(column)

            fee_text = pretty_money(fee_value)

            draw.text(pos_percent(x, rows_y[0]), pretty_money(added), font=r.font_semi, fill=FORE_COLOR, anchor='ms')
            draw.text(pos_percent(x, rows_y[1]), pretty_money(withdrawn), font=r.font_semi, fill=FORE_COLOR,
                      anchor='ms')
            draw.text(pos_percent(x, rows_y[2]), pretty_money(current), font=r.font_semi, fill=FORE_COLOR, anchor='ms')
            draw.text(pos_percent(x, rows_y[3]), fee_text, font=r.font_semi, fill=result_color(fee_value), anchor='ms')
            draw.text(pos_percent(x, rows_y[4]), pretty_money(gl, signed=True), font=r.font_semi, fill=result_color(gl),
                      anchor='ms')
        else:
            fee_text = format_percent(fee_value, current)

            r.put_hidden_plate(image, pos_percent(x, rows_y[0]), anchor='center')
            r.put_hidden_plate(image, pos_percent(x, rows_y[1]), anchor='center')
            r.put_hidden_plate(image, pos_percent(x, rows_y[2]), anchor='center')
            draw.text(pos_percent(x, rows_y[3]), fee_text, font=r.font_semi, fill=result_color(fee_value), anchor='ms')
            r.put_hidden_plate(image, pos_percent(x, rows_y[4]), anchor='center')

        if report.usd_per_asset_start is not None and report.usd_per_rune_start is not None:
            price_change = report.price_change(column)

            is_stable = column == report.USD or (column == report.ASSET and is_stable_coin(report.pool.asset))
            if not is_stable:
                draw.text(pos_percent(x, rows_y[5]), f'{pretty_money(price_change, signed=True)}%', font=r.font_semi,
                          fill=result_color(price_change), anchor='ms')
                if column == report.ASSET:
                    price_text = pretty_money(report.usd_per_asset, prefix='$')
                elif column == report.RUNE:
                    price_text = pretty_money(report.usd_per_rune, prefix='$')
                else:
                    price_text = '–'
                draw.text(pos_percent(x, rows_y[5] + 2.5),
                          f"({price_text})",
                          fill=FORE_COLOR,
                          font=r.font_small,
                          anchor='ms')
            else:
                draw.text(pos_percent(x, rows_y[5]), f'–', font=r.font_semi,
                          fill=FADE_COLOR, anchor='ms')
        else:
            draw.text(pos_percent(x, rows_y[4]), f'–', font=r.font_semi,
                      fill=FADE_COLOR, anchor='ms')

    draw.text(pos_percent(table_x, rows_y[0]), loc.LP_PIC_ADDED_VALUE, font=r.font, fill=FADE_COLOR, anchor='rs')
    draw.text(pos_percent(table_x, rows_y[1]), loc.LP_PIC_WITHDRAWN_VALUE, font=r.font, fill=FADE_COLOR, anchor='rs')
    draw.text(pos_percent(table_x, rows_y[2]), loc.LP_PIC_CURRENT_VALUE, font=r.font, fill=FADE_COLOR, anchor='rs')
    draw.text(pos_percent(table_x, rows_y[3]), loc.LP_PIC_FEES, font=r.font, fill=FADE_COLOR, anchor='rs')
    draw.text(pos_percent(table_x, rows_y[4]), loc.LP_PIC_GAIN_LOSS, font=r.font, fill=FADE_COLOR, anchor='rs')
    draw.text(pos_percent(table_x, rows_y[5]), loc.LP_PIC_PRICE_CHANGE, font=r.font, fill=FADE_COLOR, anchor='rs')
    draw.text(pos_percent(table_x, rows_y[5] + 2.5), loc.LP_PIC_PRICE_CHANGE_2, font=r.font_small, fill=FADE_COLOR,
              anchor='rs')

    # DATES
    draw.text(pos_percent(50, 92),
              loc.pic_stake_days(report.total_days, report.liq.first_stake_ts),
              anchor='ms', fill=FORE_COLOR,
              font=r.font)

    draw.text(pos_percent(50, 95),
              loc.text_stake_today(),
              anchor='ms', fill=FADE_COLOR,
              font=r.font_small)

    # LOGOS
    image.paste(rune_image, pos_percent(46, logo_y + 2, -r.LOGO_WIDTH // 2, -r.LOGO_HEIGHT // 2), rune_image)
    image.paste(asset_image, pos_percent(54, logo_y + 2, -r.LOGO_WIDTH // 2, -r.LOGO_HEIGHT // 2), asset_image)

    # ------------------------------------------------------------------------------------------------
    line3_y = logo_y - 6
    hor_line(draw, line3_y)
    # ------------------------------------------------------------------------------------------------

    # RESULTS
    lp_abs, lp_per = report.lp_vs_hold
    apy = report.lp_vs_hold_apy

    draw.text(pos_percent(20, logo_y), loc.LP_PIC_LP_VS_HOLD, anchor='ms', font=r.font_big, fill=FORE_COLOR)
    draw.text(pos_percent(80, logo_y), loc.LP_PIC_LP_APY, anchor='ms', font=r.font_big, fill=FORE_COLOR)
    draw.text(pos_percent(20, logo_y + 6), f'{pretty_money(lp_per, signed=True)} %', anchor='ms',
              fill=result_color(lp_per),
              font=r.font_big)

    if not value_hidden:
        draw.text(pos_percent(20, logo_y + 10), f'({pretty_money(lp_abs, signed=True, prefix="$")})', anchor='ms',
                  fill=result_color(lp_abs),
                  font=r.font)

    if report.total_days >= 2:
        draw.text(pos_percent(80, logo_y + 7), f'{pretty_money(apy, signed=True)} %', anchor='ms',
                  fill=result_color(apy),
                  font=r.font_big)
    else:
        draw.text(pos_percent(80, logo_y + 7), loc.LP_PIC_EARLY, anchor='ms',
                  fill=FADE_COLOR,
                  font=r.font_head)

    # FOOTER
    if loc.LP_PIC_FOOTER:
        draw.text(pos_percent(98.5, 99), loc.LP_PIC_FOOTER, anchor='rs', fill=FADE_COLOR, font=r.font_small)

    return image


async def lp_address_summary_picture(reports: List[LiquidityPoolReport], weekly_charts,
                                     loc: BaseLocalization, value_hidden=False):
    return await sync_lp_address_summary_picture(reports, weekly_charts, loc, value_hidden)


def generate_color_map(assets):
    n_colors = len(CATEGORICAL_PALETTE)
    return {asset: CATEGORICAL_PALETTE[i % n_colors] for i, asset in enumerate(assets)}


def lp_line_segments(draw, asset_values, asset_values_usd, y, value_hidden, color_map):
    res = Resources()

    segments = []
    total_usd_value = 0.0
    for asset, usd_value in asset_values_usd.items():
        asset_value = asset_values[asset]
        segments.append((asset, usd_value, asset_value))
        total_usd_value += usd_value
    segments.sort(key=operator.itemgetter(1), reverse=True)

    hp_bar_margin = 5
    hp_bar_height = 2.0
    hp_bar_width = 100 - hp_bar_margin * 2

    bar_x = hp_bar_margin
    bar_y = y

    for i, (asset, usd_value, *_) in enumerate(segments):
        segment_width = usd_value / total_usd_value * hp_bar_width
        draw.rectangle(
            (pos_percent(bar_x, bar_y), pos_percent(bar_x + segment_width, bar_y + hp_bar_height)),
            fill=color_map[asset]
        )
        bar_x += segment_width

    # line legend
    items_in_line = 4 if value_hidden else 2
    line_groups = list(grouper(items_in_line, segments))
    legend_y = y + 3.5
    legend_y_step = 3
    legend_dx = (hp_bar_width - 40) / (items_in_line - 1)
    legend_sq_w = 2
    legend_sq_h = legend_sq_w * WIDTH / HEIGHT
    counter = 0
    for line in line_groups:
        legend_x = hp_bar_margin
        for asset, usd_value, asset_value in line:
            color = CATEGORICAL_PALETTE[counter % len(CATEGORICAL_PALETTE)]
            draw.rectangle((
                pos_percent(legend_x, legend_y),
                pos_percent(legend_x + legend_sq_w, legend_y + legend_sq_h)
            ), fill=color)

            asset = RAIDO_GLYPH if is_rune(asset) else short_asset_name(asset)

            if value_hidden:
                text = asset
            else:
                text = f'{pretty_money(asset_value)} {asset} ≈ {pretty_money(usd_value, prefix="$")}'

            draw.text(pos_percent(legend_x + 3, legend_y), text, FORE_COLOR, font=res.font_small, anchor='lt')

            legend_x += legend_dx
            counter += 1
        legend_y += legend_y_step
    return len(line_groups) * legend_y_step


def lp_weekly_graph(w, h, weekly_charts: dict, color_map: dict, value_hidden):
    graph = PlotBarGraph(w, h, bg=BG_COLOR)
    graph.margin = 10

    colors = []
    dates = []
    all_series = []
    pt: LPDailyGraphPoint
    for asset, color in color_map.items():  # color_map is already sorted by $ amount
        current_chart = weekly_charts.get(asset)
        if current_chart:
            current_dates = []
            one_series = []
            current_chart = sorted(current_chart, key=operator.attrgetter('timestamp'))  # sort by date!
            for pt in current_chart:
                one_series.append(pt.usd_value)
                current_dates.append(pt.timestamp)
            dates = current_dates
            all_series.append(one_series)
            colors.append(color)

    graph.left = 152
    graph.right = 90
    graph.top = 10
    graph.n_ticks_y = 3 if value_hidden else 8
    graph.y_formatter = \
        (lambda x: '$ ???') if value_hidden else \
        (lambda x: pretty_money(x, prefix='$', short_form=True))
    graph.x_formatter = graph.date_formatter
    graph.n_ticks_x = 7

    graph.font_ticks = Resources().font_sum_ticks

    graph.plot_arrays(colors, dates, all_series)
    graph.update_bounds_y()

    graph_img = graph.finalize()
    return graph_img


@async_wrap
def sync_lp_address_summary_picture(reports: List[LiquidityPoolReport], weekly_charts, loc: BaseLocalization,
                                    value_hidden):
    total_added_value_usd = sum(r.added_value(r.USD) for r in reports)
    total_added_value_rune = sum(r.added_value(r.RUNE) for r in reports)

    total_withdrawn_value_usd = sum(r.withdrawn_value(r.USD) for r in reports)
    total_withdrawn_value_rune = sum(r.withdrawn_value(r.RUNE) for r in reports)

    total_current_value_usd = sum(r.current_value(r.USD) for r in reports)
    total_current_value_rune = sum(r.current_value(r.RUNE) for r in reports)

    asset_values = defaultdict(float)
    asset_values_usd = defaultdict(float)
    total_gain_loss_rune = 0.0
    total_gain_loss_usd = 0.0
    total_lp_vs_hold_abs = 0.0
    total_fees_usd = 0.0
    total_fees_rune = 0.0
    for r in reports:
        asset_values[r.pool.asset] += r.current_value(r.ASSET) * 0.5
        asset_values[RUNE_SYMBOL] += r.current_value(r.RUNE) * 0.5

        asset_usd_value = r.current_value(r.USD) * 0.5
        asset_values_usd[r.pool.asset] += asset_usd_value
        asset_values_usd[RUNE_SYMBOL] += asset_usd_value

        total_lp_vs_hold_abs += r.lp_vs_hold[0]

        total_gain_loss_usd += r.gain_loss(r.USD)[0]
        total_gain_loss_rune += r.gain_loss(r.RUNE)[0]
        total_fees_usd += r.fees.fee_usd
        total_fees_rune += r.fees.fee_rune

    total_fees_rune *= 2.0  # we show full rune fees because there is no split rune/asset

    total_gain_loss_usd_p = total_gain_loss_usd / total_added_value_usd * 100.0
    total_gain_loss_rune_p = total_gain_loss_rune / total_added_value_rune * 100.0
    total_lp_vs_hold_percent = total_lp_vs_hold_abs / total_added_value_usd * 100.0

    res = Resources()
    image = res.bg_image.copy()
    draw = ImageDraw.Draw(image)

    color_map = generate_color_map(asset for asset in asset_values.keys())

    # ------------------------------------------------------------------------------------------------

    # 1. Header
    run_y = 12
    hor_line(draw, run_y)

    run_y += 3.3
    draw.text(pos_percent(50, run_y), loc.LP_PIC_SUMMARY_HEADER, fill=FORE_COLOR, font=res.font_head, anchor='mm')

    pool_percents = [
        (short_asset_name(r.pool.asset), asset_values_usd[r.pool.asset] / total_current_value_usd * 2.0 * 100.0) for r
        in reports
    ]
    # pool_percents = pool_percents * 5  # debug
    pool_percents.sort(key=operator.itemgetter(1), reverse=True)

    # limit to 12 items max (2 lines by 6)
    pool_dist_str = ',\n'.join(
        ', '.join(f'{asset} ({percent:.1f}%)' for asset, percent in line) for line in grouper(6, pool_percents[:12])
    ) + '.'

    run_y += 4.7
    draw.text(pos_percent(50, run_y), pool_dist_str, fill=FADE_COLOR, font=res.font_small, anchor='mm')

    # ------------------------------------------------------------------------------------------------
    # 2. Line segments

    run_y += 3.0
    dy = lp_line_segments(draw, asset_values, asset_values_usd, run_y, value_hidden, color_map)
    run_y += dy

    # ------------------------------------------------------------------------------------------------

    # 3. Total added, total withdrawn value (USD/RUNE)
    run_y += 4.0
    hor_line(draw, run_y)
    run_y += 3.5

    if value_hidden:
        fee_percent_rune = total_fees_rune / total_current_value_rune * 100.0
        fee_percent_usd = total_fees_usd / total_current_value_usd * 100.0
        fee_rune_str = (pretty_money(fee_percent_rune, signed=True) + '%', result_color(fee_percent_rune))
        fee_usd_str = (pretty_money(fee_percent_usd, signed=True) + '%', result_color(fee_percent_usd))
    else:
        fee_rune_str = (pretty_money(total_fees_rune, signed=True, prefix=RAIDO_GLYPH), result_color(total_fees_rune))
        fee_usd_str = (pretty_money(total_fees_usd, signed=True, prefix='$'), result_color(total_fees_usd))

    data_cr = [
        [
            '',
            (loc.LP_PIC_SUMMARY_ADDED_VALUE, FADE_COLOR),
            (loc.LP_PIC_SUMMARY_WITHDRAWN_VALUE, FADE_COLOR),
            (loc.LP_PIC_SUMMARY_CURRENT_VALUE, FADE_COLOR),
            (loc.LP_PIC_FEES, FADE_COLOR),
            (loc.LP_PIC_SUMMARY_TOTAL_GAIN_LOSS, FADE_COLOR),
            (loc.LP_PIC_SUMMARY_TOTAL_GAIN_LOSS_PERCENT, FADE_COLOR)
        ],
        [
            (loc.LP_PIC_SUMMARY_AS_IF_IN_RUNE, FADE_COLOR),
            pretty_money(total_added_value_rune, prefix=RAIDO_GLYPH),
            pretty_money(total_withdrawn_value_rune, prefix=RAIDO_GLYPH),
            pretty_money(total_current_value_rune, prefix=RAIDO_GLYPH),
            fee_rune_str,
            (pretty_money(total_gain_loss_rune, signed=True, prefix=RAIDO_GLYPH), result_color(total_gain_loss_rune)),
            (pretty_money(total_gain_loss_rune_p, signed=True) + '%', result_color(total_gain_loss_rune_p))
        ],
        [
            (loc.LP_PIC_SUMMARY_AS_IF_IN_USD, FADE_COLOR),
            pretty_money(total_added_value_usd, prefix='$'),
            pretty_money(total_withdrawn_value_usd, prefix='$'),
            pretty_money(total_current_value_usd, prefix='$'),
            fee_usd_str,
            (pretty_money(total_gain_loss_usd, signed=True, prefix='$'), result_color(total_gain_loss_usd)),
            (pretty_money(total_gain_loss_usd_p, signed=True) + '%', result_color(total_gain_loss_usd_p))
        ],
    ]
    column_xs = [29, 50, 75]

    row_start_y = run_y
    row_step = 3.7
    for ic, _ in enumerate(data_cr):
        row_y = row_start_y
        for ir, _ in enumerate(data_cr[0]):
            text = data_cr[ic][ir]
            if isinstance(text, tuple):
                text, color = text
            else:
                color = FORE_COLOR

            pos = pos_percent(column_xs[ic], row_y)
            if value_hidden and ic > 0 and ir > 0 and ir != 4:  # all except first column and fees row
                res.put_hidden_plate(image, pos, 'center', ey=-20)
            else:
                draw.text(
                    pos,
                    text,
                    fill=color,
                    font=res.font,
                    anchor='mm' if ic else 'rm'
                )
            row_y += row_step
    run_y += 26.0

    # 3. Total current value USD (RUNE)
    # 4. Gain/Loss USD(RUNE) + %
    hor_line(draw, run_y)
    run_y += 3.5
    draw.text(pos_percent(50, run_y),
              loc.LP_PIC_SUMMARY_TOTAL_LP_VS_HOLD,
              fill=FORE_COLOR,
              font=res.font_head,
              anchor='mm')

    run_y += 5.0
    lp_vs_hold_y = run_y
    draw.text(pos_percent(33.3, lp_vs_hold_y),
              pretty_money(total_lp_vs_hold_percent, signed=True) + '%',
              fill=result_color(total_lp_vs_hold_percent),
              font=res.font_head, anchor='mm')

    draw.text(pos_percent(50, lp_vs_hold_y), '|', fill=FADE_COLOR, font=res.font_head, anchor='mm')

    if value_hidden:
        res.put_hidden_plate(image, pos_percent(66.6, lp_vs_hold_y), anchor='center', ey=-18)
    else:
        draw.text(pos_percent(66.6, lp_vs_hold_y),
                  pretty_money(total_lp_vs_hold_abs, signed=True, prefix='$'),
                  fill=result_color(total_lp_vs_hold_abs),
                  font=res.font_head, anchor='mm')
    run_y += 3.0

    # 5. Graph
    graph_margin_x, graph_margin_y = 1.0, 0.0
    graph_width, graph_height = pos_percent(
        100.0 - graph_margin_x * 2,
        100.0 - run_y - graph_margin_y * 2)

    if weekly_charts:
        graph_img = lp_weekly_graph(graph_width, graph_height, weekly_charts, color_map, value_hidden)
        image.paste(graph_img, pos_percent(graph_margin_x, run_y - graph_margin_y))
    else:
        draw.text(pos_percent(50, 90), loc.LP_PIC_SUMMARY_NO_WEEKLY_CHART, fill=FADE_COLOR,
                  font=res.font_head, anchor='mm')

    return image
