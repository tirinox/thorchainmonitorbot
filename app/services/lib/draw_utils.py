import logging
import math
import os
import tempfile
from colorsys import rgb_to_hls, hls_to_rgb
from io import BytesIO
from time import sleep
from typing import List, Tuple

import PIL.Image
import numpy as np
from PIL import Image, ImageDraw, ImageColor

TC_LIGHTNING_BLUE = '#00CCFF'
TC_YGGDRASIL_GREEN = '#33FF99'
TC_MIDGARD_TURQOISE = '#23DCC8'
TC_NIGHT_BLACK = '#101921'

TC_BG_COLOR = '#131920'

LINE_COLOR = '#356'

COLOR_OF_PROFIT = '#00f2c3'
COLOR_OF_LOSS = '#e22222'

LIGHT_TEXT_COLOR = 'white'

CATEGORICAL_PALETTE = [
    '#648FFF', '#785EF0',
    '#DC267F',
    '#FE6100', '#FFB000',
    '#005AB5', '#DC3220'
]

PALETTE = [
    '#66c2a5',
    '#fc8d62',
    '#8da0cb',
    '#e78ac3',
    '#a6d854',
    '#ffd92f',
    '#e5c494',
    '#b3b3b3',
]

GRADIENT_TOP_COLOR = '#0b1c27'
GRADIENT_BOTTOM_COLOR = '#11354b'


def get_palette_color_by_index(i, palette=None):
    palette = palette or PALETTE
    return palette[int(i) % len(palette)]


def hls_transform_hex(color_hex, transformer: callable):
    r, g, b = ImageColor.getrgb(color_hex)
    h, l, s = rgb_to_hls(r / 255, g / 255, b / 255)
    h, l, s = transformer(h, l, s)
    r, g, b = hls_to_rgb(h, l, s)
    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


def round_corner(radius, fill, bg):
    """Draw a round corner"""
    corner = Image.new('RGB', (radius, radius), bg)
    draw = ImageDraw.Draw(corner)
    draw.pieslice((0, 0, radius * 2, radius * 2), 180, 270, fill=fill)
    return corner


def pos_percent(x, y, ax=0, ay=0, w=1000, h=1000):
    return int(x / 100 * w + ax), int(y / 100 * h + ay)


def result_color(v):
    if v == 0.0:
        return LIGHT_TEXT_COLOR
    return COLOR_OF_LOSS if v < 0 else COLOR_OF_PROFIT


def hor_line(draw, y, width=2, w=1000, h=1000, color=LINE_COLOR):
    draw.line((pos_percent(0, y, w=w, h=h), pos_percent(100, y, w=w, h=h)), fill=color, width=width)


def generate_gradient(
        colour1: str, colour2: str, width: int, height: int) -> Image:
    """Generate a vertical gradient."""
    base = Image.new('RGB', (width, height), colour1)
    top = Image.new('RGB', (width, height), colour2)
    mask = Image.new('L', (width, height))
    mask_data = []
    for y in range(height):
        for x in range(width):
            mask_data.append(int(255 * (y / height)))
    mask.putdata(mask_data)
    base.paste(top, (0, 0), mask)
    return base


def draw_arc_aa(image, bounds, start, end, width=1, outline='white', antialias=4):
    """Improved ellipse drawing function, based on PIL.ImageDraw."""

    # Use a single channel image (mode='L') as mask.
    # The size of the mask can be increased relative to the imput image
    # to get smoother looking results.
    mask = Image.new(
        size=[int(dim * antialias) for dim in image.size],
        mode='L', color='black')
    draw = ImageDraw.Draw(mask)

    # draw outer shape in white (color) and inner shape in black (transparent)
    for offset, fill in (width / -2.0, 'white'), (width / 2.0, 'black'):
        left, top = [(value + offset) * antialias for value in bounds[:2]]
        right, bottom = [(value - offset) * antialias for value in bounds[2:]]
        draw.arc([left, top, right, bottom], start, end, fill=fill, width=width)

    # downsample the mask using PIL.Image.LANCZOS
    # (a high-quality downsampling filter).
    mask = mask.resize(image.size, Image.LANCZOS)
    # paste outline color to input image through the mask
    image.paste(outline, mask=mask)


def img_to_bio(image: PIL.Image.Image, name):
    if isinstance(image, BytesIO):
        logging.warning('Got BytesIO. Suppossed to be PIL.Image')
        return image

    bio = BytesIO()
    bio.name = name
    image.save(bio, 'PNG')
    bio.seek(0)
    return bio


def image_square_crop(im):
    width, height = im.size  # Get dimensions

    if width > height:
        new_width, new_height = height, height
    elif width < height:
        new_width, new_height = width, width
    else:
        return im

    left = int((width - new_width) / 2)
    top = int((height - new_height) / 2)
    right = int((width + new_width) / 2)
    bottom = int((height + new_height) / 2)

    # Crop the center of the image
    return im.crop((left, top, right, bottom))


def _save_image_and_show(image: Image, path):
    image.save(path, "PNG")
    os.system(f'open "{path}"')  # MacOS


def save_image_and_show(image: Image, path=None):
    if path is None:
        with tempfile.NamedTemporaryFile(suffix='.png') as f:
            _save_image_and_show(image, f.name)
            sleep(1.5)  # until it is shown by OS
    else:
        _save_image_and_show(image, path)


def rgb_to_hsv(rgb):
    # Translated from source of colorsys.rgb_to_hsv
    # r,g,b should be a numpy arrays with values between 0 and 255
    # rgb_to_hsv returns an array of floats between 0.0 and 1.0.
    rgb = rgb.astype('float')
    hsv = np.zeros_like(rgb)
    # in case an RGBA array was passed, just copy the A channel
    hsv[..., 3:] = rgb[..., 3:]
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    maxc = np.max(rgb[..., :3], axis=-1)
    minc = np.min(rgb[..., :3], axis=-1)
    hsv[..., 2] = maxc
    mask = maxc != minc
    hsv[mask, 1] = (maxc - minc)[mask] / maxc[mask]
    rc = np.zeros_like(r)
    gc = np.zeros_like(g)
    bc = np.zeros_like(b)
    rc[mask] = (maxc - r)[mask] / (maxc - minc)[mask]
    gc[mask] = (maxc - g)[mask] / (maxc - minc)[mask]
    bc[mask] = (maxc - b)[mask] / (maxc - minc)[mask]
    hsv[..., 0] = np.select(
        [r == maxc, g == maxc], [bc - gc, 2.0 + rc - bc], default=4.0 + gc - rc)
    hsv[..., 0] = (hsv[..., 0] / 6.0) % 1.0
    return hsv


def hsv_to_rgb(hsv):
    # Translated from source of colorsys.hsv_to_rgb
    # h,s should be a numpy arrays with values between 0.0 and 1.0
    # v should be a numpy array with values between 0.0 and 255.0
    # hsv_to_rgb returns an array of uints between 0 and 255.
    rgb = np.empty_like(hsv)
    rgb[..., 3:] = hsv[..., 3:]
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    i = (h * 6.0).astype('uint8')
    f = (h * 6.0) - i
    p = v * (1.0 - s)
    q = v * (1.0 - s * f)
    t = v * (1.0 - s * (1.0 - f))
    i %= 6
    conditions = [s == 0.0, i == 1, i == 2, i == 3, i == 4, i == 5]
    rgb[..., 0] = np.select(conditions, [v, q, p, p, t, v], default=v)
    rgb[..., 1] = np.select(conditions, [v, v, v, q, p, p], default=t)
    rgb[..., 2] = np.select(conditions, [v, p, t, v, v, q], default=p)
    return rgb.astype('uint8')


def shift_hue(arr, hout):
    hsv = rgb_to_hsv(arr)
    hsv[..., 0] = hout
    rgb = hsv_to_rgb(hsv)
    return rgb


def shift_hue_image(img: Image, hue_out):
    arr = np.array(img)
    return Image.fromarray(shift_hue(arr, hue_out), 'RGBA')


def transform_colors_hvs(img: Image, func):
    arr = np.array(img)
    hsv = rgb_to_hsv(arr)
    hsv = func(hsv)
    rgb = hsv_to_rgb(hsv)
    return Image.fromarray(rgb, 'RGBA')


def default_gradient(w, h):
    return generate_gradient(GRADIENT_TOP_COLOR, GRADIENT_BOTTOM_COLOR, w, h)


def default_background(w, h):
    return Image.new('RGBA', (w, h), color=TC_BG_COLOR)


class CacheGrid:
    def __init__(self, scale_x=10, scale_y=10):
        self.scale_x = scale_x
        self.scale_y = scale_y
        self._s = set()

    def key(self, x, y):
        x /= self.scale_x
        y /= self.scale_y

        return f'{int(x)}-{int(y)}'

    def is_occupied(self, x, y):
        return self.key(x, y) in self._s

    def set(self, x, y, v=True):
        k = self.key(x, y)
        if v:
            self._s.add(k)
        elif k in self._s:
            self._s.remove(k)


def radial_pos_int(cx, cy, r, angle_deg):
    a = angle_deg / 180 * math.pi
    x = cx + r * math.cos(a)
    y = cy + r * math.sin(a)
    return int(x), int(y)


def make_donut_chart(elements: List[Tuple[str, int]],
                     width=400, margin=4, line_width=40, gap=1, label_r=0,
                     title_color=LIGHT_TEXT_COLOR,
                     font_middle=None,
                     font_abs_count=None,
                     font_percent=None,
                     palette=None,
                     title=None,
                     bg_color=(0, 0, 0, 0)):
    image = Image.new('RGBA', (width, width), bg_color)
    draw = ImageDraw.Draw(image)

    elements = [item for item in elements if item[1] > 0]  # filter out bad values
    total_count = sum(item[1] for item in elements)
    if not total_count:
        return image  # nothing to plot!

    cx = cy = width // 2

    half_line_width = line_width // 2
    ellipse_bbox = [
        margin + half_line_width,
        margin + half_line_width,
        width - margin - half_line_width,
        width - margin - half_line_width
    ]

    gap *= 0.5

    current = 0
    deg_per_one = 360 / total_count
    for i, (label, value) in enumerate(elements):
        arc_len = deg_per_one * value

        color = palette(i) if palette else get_palette_color_by_index(i)

        arc_start = current + gap
        arc_end = current + arc_len - gap
        if arc_start < arc_end:
            draw_arc_aa(image, ellipse_bbox,
                        arc_start, arc_end,
                        line_width, color)

        if font_abs_count:
            r = label_r if label_r else (margin + line_width)
            x, y = radial_pos_int(cx, cy, r, current + arc_len / 2)
            draw.text((x, y),
                      str(value),
                      font=font_abs_count, fill=color, anchor='mm')

        if font_percent:
            x, y = radial_pos_int(cx, cy, width // 2 - margin - line_width * 0.6, current + arc_len / 2)
            draw.text((x, y), f"{int(value / total_count * 100.)}%", color, font=font_percent, anchor='mm')

        current += arc_len

    if title_color and font_middle:
        title = title or str(total_count)
        draw.text((cx, cy), title, fill=title_color, font=font_middle, anchor='mm')

    return image
