import math
import os
import tempfile
from colorsys import rgb_to_hls, hls_to_rgb
from io import BytesIO
from time import sleep

from PIL import Image, ImageDraw, ImageColor

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


def get_palette_color_by_index(i):
    return PALETTE[int(i) % len(PALETTE)]


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


def img_to_bio(image, name):
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
