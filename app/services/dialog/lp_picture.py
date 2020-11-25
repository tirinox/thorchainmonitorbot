import asyncio
import datetime
import logging
import os
from io import BytesIO
from math import ceil

import aiofiles as aiofiles
import aiohttp
from PIL import Image, ImageDraw, ImageFont

from services.lib.money import asset_name_cut_chain, pretty_money
from services.models.stake_info import StakePoolReport
from services.models.time_series import BNB_SYMBOL, RUNE_SYMBOL

COIN_LOGO = 'https://raw.githubusercontent.com/trustwallet/assets/master/blockchains/binance/assets/{asset}/logo.png'
LOCAL_COIN_LOGO = '../data/{asset}.png'
UNKNOWN_LOGO = '../data/unknown.png'
HIDDEN_IMG = '../data/hidden.png'
BG_IMG = '../data/lp_bg.png'

FONT_BOLD = '../data/my.ttf'

WIDTH, HEIGHT = 600, 800
LOGO_WIDTH, LOGO_HEIGHT = 64, 64

BG_COLOR = (25, 25, 25, 255)
LINE_COLOR = '#356'
GREEN_COLOR = '#00f2c3'
RED_COLOR = '#e22222'
FORE_COLOR = 'white'
FADE_COLOR = '#cccccc'
RAIDO_GLYPH = 'ᚱ'


def round_corner(radius, fill, bg):
    """Draw a round corner"""
    corner = Image.new('RGB', (radius, radius), bg)
    draw = ImageDraw.Draw(corner)
    draw.pieslice((0, 0, radius * 2, radius * 2), 180, 270, fill=fill)
    return corner


def round_rectangle(size, radius, fill, bg=BG_COLOR):
    """Draw a rounded rectangle"""
    width, height = size
    rectangle = Image.new('RGB', size, fill)
    corner = round_corner(radius, fill, bg)
    rectangle.paste(corner, (0, 0))
    rectangle.paste(corner.rotate(90), (0, height - radius))  # Rotate the corner and paste it
    rectangle.paste(corner.rotate(180), (width - radius, height - radius))
    rectangle.paste(corner.rotate(270), (width - radius, 0))
    return rectangle


def image_url(asset):
    if asset == BNB_SYMBOL:
        return 'https://s2.coinmarketcap.com/static/img/coins/200x200/1839.png'
    else:
        return COIN_LOGO.format(asset=asset_name_cut_chain(asset))


async def download_logo(asset):
    async with aiohttp.ClientSession() as session:
        url = image_url(asset)
        logging.info(f'Downloading logo for {asset} from {url}...')
        async with session.get(url) as resp:
            if resp.status == 200:
                f = await aiofiles.open(LOCAL_COIN_LOGO.format(asset=asset), mode='wb')
                await f.write(await resp.read())
                await f.close()


async def download_logo_cached(asset):
    try:
        local_path = LOCAL_COIN_LOGO.format(asset=asset)
        if not os.path.exists(local_path):
            await download_logo(asset)
        logo = Image.open(local_path).convert("RGBA")
    except:
        logo = Image.open(UNKNOWN_LOGO)
        logging.exception('')
    logo.thumbnail((LOGO_WIDTH, LOGO_HEIGHT))
    return logo


def pos_percent(x, y, ax=0, ay=0, w=WIDTH, h=HEIGHT):
    return int(x / 100 * w + ax), int(y / 100 * h + ay)


def result_color(v):
    return RED_COLOR if v < 0 else GREEN_COLOR


async def lp_pool_picture(report: StakePoolReport, value_hidden=False):
    asset = report.pool.asset
    rune_image, asset_image = await asyncio.gather(
        download_logo_cached(RUNE_SYMBOL),
        download_logo_cached(asset)
    )

    hidden_img = Image.open(HIDDEN_IMG)  # if value_hidden else None
    hidden_img.thumbnail((100, 24))

    font = ImageFont.truetype(FONT_BOLD, 20)
    font_head = ImageFont.truetype(FONT_BOLD, 24)
    font_small = ImageFont.truetype(FONT_BOLD, 14)
    font_semi = ImageFont.truetype(FONT_BOLD, 16)
    image = Image.open(BG_IMG)
    # image = Image.new('RGBA', (WIDTH, HEIGHT), color=BG_COLOR)
    draw = ImageDraw.Draw(image)

    left, center, right = 30, 50, 70
    head_y = 8
    dy = 6
    line1_y = 12
    logo_y = 82
    start_y = line1_y + dy

    # HEADER
    draw.text(pos_percent(center, head_y), 'POOL', font=font_head, fill=FADE_COLOR, anchor='ms')
    draw.text(pos_percent(left, head_y), 'RUNE', font=font_head, fill=FORE_COLOR, anchor='rs')
    draw.text(pos_percent(right, head_y), asset_name_cut_chain(asset), font=font, fill=FORE_COLOR, anchor='ls')
    draw.line((pos_percent(0, line1_y), pos_percent(100, line1_y)), fill=LINE_COLOR, width=2)

    # ADDED
    draw.text(pos_percent(center, start_y), 'Added', font=font, fill=FADE_COLOR, anchor='ms')
    draw.text(pos_percent(left, start_y), f'{pretty_money(report.liq.rune_stake)} {RAIDO_GLYPH}', font=font,
              fill=FORE_COLOR,
              anchor='rs')
    draw.text(pos_percent(right, start_y), f'{pretty_money(report.liq.asset_stake)}', font=font, fill=FORE_COLOR,
              anchor='ls')
    start_y += dy

    # WITHDRAWN
    draw.text(pos_percent(center, start_y), 'Withdrawn', font=font, fill=FADE_COLOR, anchor='ms')
    draw.text(pos_percent(left, start_y), f'{pretty_money(report.liq.rune_withdrawn)} {RAIDO_GLYPH}', font=font,
              fill=FORE_COLOR,
              anchor='rs')
    draw.text(pos_percent(right, start_y), f'{pretty_money(report.liq.asset_withdrawn)}', font=font, fill=FORE_COLOR,
              anchor='ls')
    start_y += dy

    # REDEEMABLE
    draw.text(pos_percent(center, start_y), 'Redeemable', font=font, fill=FADE_COLOR, anchor='ms')
    redeem_rune, redeem_asset = report.redeemable_rune_asset
    draw.text(pos_percent(left, start_y), f'{pretty_money(redeem_rune)} {RAIDO_GLYPH}', font=font,
              fill=FORE_COLOR,
              anchor='rs')
    draw.text(pos_percent(right, start_y), f'{pretty_money(redeem_asset)}', font=font, fill=FORE_COLOR,
              anchor='ls')
    start_y += dy

    # GAIN LOSS
    draw.text(pos_percent(center, start_y), 'Gain / Loss', font=font, fill=FADE_COLOR, anchor='ms')
    gl_rune, gl_rune_per, gl_asset, gl_asset_per = report.gain_loss_raw
    draw.text(pos_percent(left, start_y), f'{pretty_money(gl_rune, signed=True)} {RAIDO_GLYPH}', font=font,
              fill=result_color(gl_rune),
              anchor='rs')
    draw.text(pos_percent(right, start_y), f'{pretty_money(gl_asset, signed=True)}', font=font,
              fill=result_color(gl_asset),
              anchor='ls')
    start_y += 4

    # GAIN LOSS PERCENT
    gl_usd, gl_usd_p = report.gain_loss(report.USD)
    draw.text(pos_percent(center, start_y), f'{pretty_money(gl_usd_p, signed=True)}% in $USD', font=font,
              fill=result_color(gl_usd_p),
              anchor='ms')

    draw.text(pos_percent(left, start_y), f'{pretty_money(gl_rune_per, signed=True)}%', font=font,
              fill=result_color(gl_rune_per),
              anchor='rs')
    draw.text(pos_percent(right, start_y), f'{pretty_money(gl_asset_per, signed=True)}%', font=font,
              fill=result_color(gl_asset_per),
              anchor='ls')
    start_y += 4

    draw.line((pos_percent(0, start_y), pos_percent(100, start_y)), fill=LINE_COLOR, width=2)
    start_y += 5

    # VALUE
    table_x = 30
    columns_x = [44 + c * 19 for c in range(3)]
    rows_y = [start_y + 4 + r * 3.5 for r in range(5)]

    draw.text(pos_percent(columns_x[0], start_y), f'{RAIDO_GLYPH}une', font=font, fill=FADE_COLOR, anchor='ms')
    draw.text(pos_percent(columns_x[1], start_y), asset_name_cut_chain(asset), font=font, fill=FADE_COLOR, anchor='ms')
    draw.text(pos_percent(columns_x[2], start_y), 'USD', font=font, fill=FADE_COLOR, anchor='ms')

    columns = (report.RUNE, report.ASSET, report.USD)
    for x, column in zip(columns_x, columns):
        added = report.added_value(column)
        withdrawn = report.withdrawn_value(column)
        current = report.current_value(column)
        gl, _ = report.gain_loss(column)

        draw.text(pos_percent(x, rows_y[0]), pretty_money(added), font=font_semi, fill=FORE_COLOR, anchor='ms')
        draw.text(pos_percent(x, rows_y[1]), pretty_money(withdrawn), font=font_semi, fill=FORE_COLOR, anchor='ms')
        draw.text(pos_percent(x, rows_y[2]), pretty_money(current), font=font_semi, fill=FORE_COLOR, anchor='ms')
        draw.text(pos_percent(x, rows_y[3]), pretty_money(gl, signed=True), font=font_semi, fill=result_color(gl),
                  anchor='ms')

        if report.usd_per_asset_start is not None and report.usd_per_rune_start is not None:
            price_change = report.price_change(column)

            if column != report.USD:
                draw.text(pos_percent(x, rows_y[4]), f'{pretty_money(price_change, signed=True)}%', font=font_semi,
                          fill=result_color(price_change), anchor='ms')
            else:
                draw.text(pos_percent(x, rows_y[4]), f'–', font=font_semi,
                          fill=FADE_COLOR, anchor='ms')
        else:
            draw.text(pos_percent(x, rows_y[4]), f'–', font=font_semi,
                      fill=FADE_COLOR, anchor='ms')

    draw.text(pos_percent(table_x, rows_y[0]), 'Added value', font=font, fill=FADE_COLOR, anchor='rs')
    draw.text(pos_percent(table_x, rows_y[1]), 'Withdrawn value', font=font, fill=FADE_COLOR, anchor='rs')
    draw.text(pos_percent(table_x, rows_y[2]), 'Current value', font=font, fill=FADE_COLOR, anchor='rs')
    draw.text(pos_percent(table_x, rows_y[3]), 'Gain / Loss', font=font, fill=FADE_COLOR, anchor='rs')
    draw.text(pos_percent(table_x, rows_y[4]), 'Price change', font=font, fill=FADE_COLOR, anchor='rs')

    start_date = datetime.datetime.fromtimestamp(report.liq.first_stake_ts).strftime('%d.%m.%Y')
    draw.text(pos_percent(50, 92),
              f'{ceil(report.total_days)} days ({start_date})',
              anchor='ms', fill=FORE_COLOR,
              font=font_small)

    # LOGOS
    image.paste(rune_image, pos_percent(46, logo_y + 2, -LOGO_WIDTH // 2, -LOGO_HEIGHT // 2), rune_image)
    image.paste(asset_image, pos_percent(54, logo_y + 2, -LOGO_WIDTH // 2, -LOGO_HEIGHT // 2), asset_image)

    # RESULTS
    line3_y = logo_y - 6
    draw.line((pos_percent(0, line3_y), pos_percent(100, line3_y)), fill=LINE_COLOR, width=2)

    lp_abs, lp_per = report.lp_vs_hold
    apy = report.lp_vs_hold_apy
    font_big = ImageFont.truetype(FONT_BOLD, 32)
    draw.text(pos_percent(20, logo_y), 'LP vs HOLD', anchor='ms', font=font_big, fill=FORE_COLOR)
    draw.text(pos_percent(80, logo_y), 'LP APY', anchor='ms', font=font_big, fill=FORE_COLOR)
    draw.text(pos_percent(20, logo_y + 6), f'{pretty_money(lp_per, signed=True)} %', anchor='ms',
              fill=result_color(lp_per),
              font=font_big)
    draw.text(pos_percent(20, logo_y + 10), f'({pretty_money(lp_abs, signed=True, prefix="$")})', anchor='ms',
              fill=result_color(lp_abs),
              font=font)

    if report.total_days >= 2:
        draw.text(pos_percent(80, logo_y + 7), f'{pretty_money(apy, signed=True)} %', anchor='ms',
                  fill=result_color(apy),
                  font=font_big)
    else:
        draw.text(pos_percent(80, logo_y + 7), f'Early...', anchor='ms',
                  fill=FADE_COLOR,
                  font=font_head)

    # FOOTER

    draw.text(pos_percent(98, 98), f"Powered by BigBoss' runestake.info", anchor='rs', fill=FADE_COLOR, font=font_small)

    # image.paste(hidden_img, (100, 400), hidden_img)
    return image


def img_to_bio(image, name):
    bio = BytesIO()
    bio.name = name  # f'lp_report_{report.pool}.png'
    image.save(bio, 'PNG')
    bio.seek(0)
    return bio
