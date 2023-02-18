import logging
import math
import os
import tempfile
from collections import defaultdict
from colorsys import rgb_to_hls, hls_to_rgb
from io import BytesIO
from time import sleep
from typing import List, Tuple

import PIL.Image
import numpy as np
from PIL import Image, ImageDraw, ImageColor

from services.lib.money import clamp
from services.lib.utils import linear_transform

TC_LIGHTNING_BLUE = '#00CCFF'
TC_YGGDRASIL_GREEN = '#33FF99'
TC_MIDGARD_TURQOISE = '#23DCC8'
TC_NIGHT_BLACK = '#101921'

MY_PURPLE = '#6d3bdf'
MY_PURPLE_2 = '#af2fcc'

TC_BG_COLOR = '#131920'

TC_WHITE = '#f0f0f0'

LINE_COLOR = '#356'

COLOR_OF_PROFIT = '#00f2c3'
COLOR_OF_LOSS = '#e22222'

LIGHT_TEXT_COLOR = TC_WHITE

CATEGORICAL_PALETTE = [
    '#648FFF',
    '#785EF0',
    '#DC267F',
    '#FE6100',
    '#FFB000',
    '#005AB5',
    '#DC3220'
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


def rgb(r, g, b):
    return r, g, b


NEW_PALETTE = [
    rgb(0, 43, 91),
    rgb(43, 72, 101),
    rgb(37, 109, 133),
    rgb(143, 227, 207),
]

TC_PALETTE = [
    TC_LIGHTNING_BLUE,
    TC_YGGDRASIL_GREEN,
    TC_MIDGARD_TURQOISE,
    MY_PURPLE,
    MY_PURPLE_2,
    '#dbc221',
]


def hex_to_rgb(value):
    value = value.lstrip('#')
    lv = len(value)
    return tuple(int(value[i:i + lv // 3], 16) for i in range(0, lv, lv // 3))


def get_palette_color_by_index_new(i, palette, step=0.5):
    n = len(palette)
    location = i * step
    index = int(location) % n
    t = location - int(location)
    next_index = (index + 1) % n
    c1 = palette[index]
    c2 = palette[next_index]
    if isinstance(c1, str):
        c1 = hex_to_rgb(c1)
    if isinstance(c2, str):
        c2 = hex_to_rgb(c2)
    r, g, b = [int(linear_transform(t, 0.0, 1.0, c1[i], c2[i]))
               for i in range(3)]
    return r, g, b


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
    # noinspection PyTypeChecker
    draw.pieslice((0, 0, radius * 2, radius * 2), 180, 270, fill=fill)
    return corner


def pos_percent(x, y, ax=0, ay=0, w=1000, h=1000):
    return int(x / 100 * w + ax), int(y / 100 * h + ay)


def result_color(v, min_ch=0.000001):
    if abs(v) <= min_ch:
        return LIGHT_TEXT_COLOR
    return COLOR_OF_LOSS if v < min_ch else COLOR_OF_PROFIT


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
        v = int(255 * (y / height))
        for x in range(width):
            mask_data.append(v)
    mask.putdata(mask_data)
    base.paste(top, (0, 0), mask)
    return base


def draw_arc_aa(image, bounds, start, end, width=1, outline=TC_WHITE, antialias=4):
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
    if not image:
        logging.error('Nothing to save!')
        return

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
        self._s = defaultdict(float)

    def clear(self):
        self._s.clear()

    def key(self, x, y):
        x /= self.scale_x
        y /= self.scale_y
        return int(x), int(y)

    def is_occupied(self, x, y):
        return self.key(x, y) in self._s

    def set(self, x, y, v=True):
        k = self.key(x, y)
        if v is not None:
            self._s[k] = v
        elif k in self._s:
            del self._s[k]
        return k

    def inc(self, x, y, v=1.0):
        k = self.key(x, y)
        self._s[k] += v
        return k

    def __getitem__(self, item):
        return self._s[item]

    def get(self, x, y):
        return self._s.get(self.key(x, y))

    def box_guts(self, xy):
        (x1, y1), (x2, y2) = xy
        if x2 <= x1 or y2 <= y1:
            return

        y = y1
        while y < y2:
            x = x1
            while x < x2:
                yield x, y
                x += self.scale_x
            y += self.scale_y

    def fill_box(self, xy, v=True):
        for x, y in self.box_guts(xy):
            self.set(x, y, v)

    def is_box_occupied(self, xy):
        return any(self.is_occupied(x, y) for x, y in self.box_guts(xy))


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
                     palette=get_palette_color_by_index,
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

        color = palette(i)

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


def line_progress_bar(draw: ImageDraw,
                      value: float, xy, line_width=1, gap=1,
                      color_filled='#fff', color_unfilled='#777'):
    (x_start, y), (w, h) = xy
    if w <= 0 or h <= 0:
        return
    x = x_start
    x_end = x + w
    y_end = y + h
    value = clamp(value, 0.0, 1.0)

    while x <= x_end:
        progress = (x - x_start) / w
        color = color_filled if progress <= value else color_unfilled
        draw.line(((x, y), (x, y_end)), width=line_width, fill=color)
        x += line_width + gap


def paste_image_masked(destination, source, xy, anchor='mm'):
    x_anchor, y_anchor = anchor.lower()
    w, h = source.width, source.height
    ox, oy = xy

    if x_anchor == 'm':
        x = ox - w // 2
    elif x_anchor == 'l':
        x = ox
    elif x_anchor == 'r':
        x = ox - w
    else:
        raise ValueError(f'unknown X anchor "{x_anchor}"')

    if y_anchor == 'm':
        y = oy - h // 2
    elif y_anchor == 't':
        y = oy
    elif y_anchor == 'b':
        y = oy - h
    else:
        raise ValueError(f'unknown Y anchor "{y_anchor}"')

    destination.paste(source, (x, y), source)
    return destination


def measure_font_to_fit_in_box(font_getter, text, max_width, max_height, current_font_size=None, f=0.92):
    current_font_size = current_font_size or min(max_width, max_height)

    if current_font_size < 4:
        return None

    font = font_getter(int(current_font_size))
    w, h = font.getsize(text)
    if w > max_width or h > max_height:
        return measure_font_to_fit_in_box(font_getter, text, max_width, max_height, current_font_size * f)

    return font, w, h


def convert_indexed_png(indexed):
    if indexed.mode == "P":
        # check if transparent
        is_transparent = indexed.info.get("transparency", False)

        if is_transparent is False:
            # if not transparent, convert indexed image to RGB
            return indexed.convert("RGB")
        else:
            # convert indexed image to RGBA
            return indexed.convert("RGBA")
    elif indexed.mode == 'PA':
        return indexed.convert("RGBA")
    else:
        # the mode is not indexed
        return indexed
