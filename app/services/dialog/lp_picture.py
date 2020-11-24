import asyncio
import logging
import os
from io import BytesIO

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

FONT_BOLD = '../data/my.ttf'

WIDTH, HEIGHT = 600, 800
LOGO_WIDTH, LOGO_HEIGHT = 64, 64

BG_COLOR = (25, 25, 25, 255)
LINE_COLOR = '#666'
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
    image = Image.new('RGBA', (WIDTH, HEIGHT), color=BG_COLOR)
    draw = ImageDraw.Draw(image)

    left, right = 30, 70

    # HEADER
    draw.text(pos_percent(50, 8), 'POOL', font=font, fill=FADE_COLOR, anchor='ms')
    draw.text(pos_percent(left, 8), 'RUNE', font=font, fill=FORE_COLOR, anchor='rs')
    draw.text(pos_percent(right, 8), asset_name_cut_chain(asset), font=font, fill=FORE_COLOR, anchor='ls')
    draw.line((pos_percent(0, 12), pos_percent(100, 12)), fill=LINE_COLOR, width=2)

    # ADDED
    draw.text(pos_percent(50, 18), 'Added', font=font, fill=FADE_COLOR, anchor='ms')
    draw.text(pos_percent(left, 18), f'{pretty_money(report.liq.rune_stake)} {RAIDO_GLYPH}', font=font, fill=FORE_COLOR,
              anchor='rs')
    draw.text(pos_percent(right, 18), f'{pretty_money(report.liq.asset_stake)}', font=font, fill=FORE_COLOR,
              anchor='ls')

    # WITHDRAWN
    draw.text(pos_percent(50, 24), 'Withdrawn', font=font, fill=FADE_COLOR, anchor='ms')
    draw.text(pos_percent(left, 24), f'{pretty_money(report.liq.rune_withdrawn)} {RAIDO_GLYPH}', font=font,
              fill=FORE_COLOR,
              anchor='rs')
    draw.text(pos_percent(right, 24), f'{pretty_money(report.liq.asset_withdrawn)}', font=font, fill=FORE_COLOR,
              anchor='ls')

    # REDEEMABLE
    draw.text(pos_percent(50, 30), 'Redeemable', font=font, fill=FADE_COLOR, anchor='ms')
    redeem_rune, redeem_asset = report.redeemable_rune_asset
    draw.text(pos_percent(left, 30), f'{pretty_money(redeem_rune)} {RAIDO_GLYPH}', font=font,
              fill=FORE_COLOR,
              anchor='rs')
    draw.text(pos_percent(right, 30), f'{pretty_money(redeem_asset)}', font=font, fill=FORE_COLOR,
              anchor='ls')

    # GAIN LOSS
    draw.text(pos_percent(50, 36), 'Gain / loss', font=font, fill=FADE_COLOR, anchor='ms')
    gl_rune = report.liq.rune_withdrawn + redeem_rune - report.liq.rune_stake
    gl_asset = report.liq.asset_withdrawn + redeem_asset - report.liq.asset_stake
    draw.text(pos_percent(left, 36), f'{pretty_money(gl_rune)} {RAIDO_GLYPH}', font=font,
              fill=result_color(gl_rune),
              anchor='rs')
    draw.text(pos_percent(right, 36), f'{pretty_money(gl_asset)}', font=font,
              fill=result_color(gl_asset),
              anchor='ls')

    # LOGOS
    image.paste(rune_image, pos_percent(46, 50, -LOGO_WIDTH // 2, -LOGO_HEIGHT // 2), rune_image)
    image.paste(asset_image, pos_percent(54, 50, -LOGO_WIDTH // 2, -LOGO_HEIGHT // 2), asset_image)

    # RESULTS
    lp_abs, lp_per = report.lp_vs_hold
    apy = report.lp_vs_hold_apy
    font_big = ImageFont.truetype(FONT_BOLD, 32)
    draw.text(pos_percent(left, 75), 'LP vs HOLD', anchor='ms', font=font_big, fill=FORE_COLOR)
    draw.text(pos_percent(right, 75), 'LP APY', anchor='ms', font=font_big, fill=FORE_COLOR)

    # todo! test signed ++++ plus!!!
    draw.text(pos_percent(left, 80), f'{pretty_money(lp_per, signed=True)} %', anchor='ms', fill=result_color(lp_per),
              font=font_big)
    draw.text(pos_percent(right, 80), f'{pretty_money(apy, signed=True)} %', anchor='ms', fill=result_color(apy), font=font_big)

    # image.paste(hidden_img, (100, 400), hidden_img)
    return image


def img_to_bio(image, name):
    bio = BytesIO()
    bio.name = name  # f'lp_report_{report.pool}.png'
    image.save(bio, 'PNG')
    bio.seek(0)
    return bio
