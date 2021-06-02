import math
from io import BytesIO

from PIL import Image, ImageDraw

from services.dialog.picture.lp_picture import LP_PIC_WIDTH, LP_PIC_HEIGHT, LINE_COLOR

COLOR_OF_PROFIT = '#00f2c3'
COLOR_OF_LOSS = '#e22222'

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


def round_corner(radius, fill, bg):
    """Draw a round corner"""
    corner = Image.new('RGB', (radius, radius), bg)
    draw = ImageDraw.Draw(corner)
    draw.pieslice((0, 0, radius * 2, radius * 2), 180, 270, fill=fill)
    return corner


def pos_percent(x, y, ax=0, ay=0, w=LP_PIC_WIDTH, h=LP_PIC_HEIGHT):
    return int(x / 100 * w + ax), int(y / 100 * h + ay)


def result_color(v):
    return COLOR_OF_LOSS if v < 0 else COLOR_OF_PROFIT


def hor_line(draw, y, width=2, w=LP_PIC_WIDTH, h=LP_PIC_HEIGHT):
    draw.line((pos_percent(0, y, w=w, h=h), pos_percent(100, y, w=w, h=h)), fill=LINE_COLOR, width=width)


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


def arc(draw, bbox, start, end, fill, width=1, segments=100):
    """
    Hack that looks similar to PIL's draw.arc(), but can specify a line width.
    """
    # radians
    start *= math.pi / 180
    end *= math.pi / 180

    # angle step
    da = (end - start) / segments

    # shift end points with half a segment angle
    start -= da / 2
    end -= da / 2

    # ellips radii
    rx = (bbox[2] - bbox[0]) / 2
    ry = (bbox[3] - bbox[1]) / 2

    # box centre
    cx = bbox[0] + rx
    cy = bbox[1] + ry

    # segment length
    l = (rx + ry) * da / 2.0

    for i in range(segments):
        # angle centre
        a = start + (i + 0.5) * da

        # x,y centre
        x = cx + math.cos(a) * rx
        y = cy + math.sin(a) * ry

        # derivatives
        dx = -math.sin(a) * rx / (rx + ry)
        dy = math.cos(a) * ry / (rx + ry)

        draw.line([(x - dx * l, y - dy * l), (x + dx * l, y + dy * l)], fill=fill, width=width)


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
