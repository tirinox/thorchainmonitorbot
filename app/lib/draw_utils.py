import collections
import colorsys
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
from PIL import Image, ImageDraw, ImageColor, ImageFilter, ImageFont

from lib.money import clamp
from lib.utils import linear_transform

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
GRADIENT_BOTTOM_COLOR = '#060f14'


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
    # noinspection PyTypeChecker
    mask = Image.new(
        size=[int(dim * antialias) for dim in image.size],
        mode='L', color='black')
    draw = ImageDraw.Draw(mask)

    # draw outer shape in white (color) and inner shape in black (transparent)
    for offset, fill in (width / -2.0, 'white'), (width / 2.0, 'black'):
        left, top = [(value + offset) * antialias for value in bounds[:2]]
        right, bottom = [(value - offset) * antialias for value in bounds[2:]]

        if left > right:
            left, right = right, left
        if top > bottom:
            top, bottom = bottom, top

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
        logging.warning('Got BytesIO. Supposed to be PIL.Image')
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
    return hsv_to_rgb(hsv)


def adjust_brightness(color, factor):
    # Convert the HEX color to RGB
    if isinstance(color, str):
        hex_color = color.lstrip('#')
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        as_tuple = False
    else:
        r, g, b = color
        as_tuple = True

    # Adjust the brightness by scaling the RGB values
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)

    # Adjust brightness (value) while keeping hue and saturation constant
    v = max(0, min(1, v * factor))

    # Convert HSV back to RGB
    r, g, b = [int(c * 255) for c in colorsys.hsv_to_rgb(h, s, v)]

    if as_tuple:
        return r, g, b
    else:
        # Convert the adjusted RGB values back to HEX
        return "#{:02X}{:02X}{:02X}".format(r, g, b)


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


def rect_progress_bar(draw: ImageDraw,
                      value: float, xy, line_width=1, gap=1,
                      color_filled='#fff', color_unfilled='#777', radius=6):
    (x_start, y), (w, h) = xy
    if w <= 0 or h <= 0:
        return
    x = x_start
    x_end = x + w
    y_end = y + h
    value = clamp(value, 0.0, 1.0)

    x_middle = w * value + x
    margin = 2

    draw: ImageDraw
    draw.rounded_rectangle((x - margin, y - margin, x_end + margin, y_end + margin), radius, fill=color_unfilled)

    if x_middle < x:
        x_middle, x = x, x_middle

    try:
        if abs(x_middle - x) <= radius * 3:
            draw.rectangle((x, y, x_middle, y_end), fill=color_filled)
        else:
            draw.rounded_rectangle((x, y, x_middle, y_end), radius, fill=color_filled)
    except ValueError:
        pass


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
    w, h = font_estimate_size(font, text)

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


def dual_side_rect(draw: ImageDraw, x1, y1, x2, y2, a, b, a_color='#0f0', b_color='#00f', gap=2):
    s = a + b
    if s == 0:
        return
    w = x2 - x1
    x_mid = int(w * a / s)
    draw.rectangle(
        (x1, y1, x_mid + x1 - gap, y2), fill=a_color
    )
    draw.rectangle(
        (x_mid + x1 + gap, y1, x2, y2), fill=b_color
    )


def distribution_bar_chart(draw: ImageDraw, values, x, y, width, height, palette=None, gap=2):
    assert width > 0 and height > 0

    n = len(values)
    total = sum(values)
    if total == 0:
        return

    if not palette:
        palette = CATEGORICAL_PALETTE

    total_gaps = n - 1
    available_width = width - total_gaps * gap

    x_current = x

    for i, value in enumerate(values):
        color = palette[i % len(palette)]
        wi = int(value / total * available_width)
        draw.rectangle((x_current, y, x_current + wi, y + height), fill=color, outline=color)
        x_current += gap + wi


def font_estimate_size(font, text):
    if hasattr(font, 'getsize'):
        tw, th = font.getsize(text)
        return tw, th
    else:
        left, top, right, bottom = font.getbbox(text)
        return right - left, bottom - top


def reduce_alpha(im: Image, target_alpha=0.5):
    na = np.array(im)

    # Make alpha 128 anywhere is is non-zero
    # na[..., 3] = target_alpha * (na[..., 3] > 0)
    na[..., 3] = target_alpha * na[..., 3]

    # Convert back to PIL Image
    return Image.fromarray(na)


def add_shadow(image, size=10, shadow_source=None):
    shadow_source = shadow_source or image
    # Adjust the radius for the desired softness
    shadow = shadow_source.filter(ImageFilter.GaussianBlur(radius=size))

    shadow.paste((255, 255, 255, 255), (0, 0, shadow.width, shadow.height), image)
    return shadow


def add_transparent_frame(image, left, top=None, right=None, bottom=None):
    if top is None:
        top = left
    if right is None:
        right = left
    if bottom is None:
        bottom = top

    new_width = image.width + left + right
    new_height = image.height + top + bottom

    # Create a new blank image with an alpha channel
    frame = Image.new('RGBA', (new_width, new_height), (0, 0, 0, 0))

    # Paste the original image onto the frame, with an offset to center it
    offset = ((new_width - image.width) // 2, (new_height - image.height) // 2)
    frame.paste(image, offset)
    return frame


def add_tint_to_bw_image(img, tint_color):
    # Ensure the image is in grayscale
    if img.mode != 'L':
        img = img.convert('L')

    # Create a new image with the same size and tint color
    tinted_img = Image.new('RGB', img.size, tint_color)

    # Apply the grayscale image as an alpha mask
    tinted_img.putalpha(img)

    return tinted_img


def get_dominant_colors(img, num_colors=5, thumb_size=60, threshold=100):
    # Resize the image for faster processing if needed
    img = img.copy()
    img.thumbnail((thumb_size, thumb_size))

    # Convert the image to RGB mode
    img = img.convert("RGB")

    # Get the image data as a list of RGB tuples
    pixels = list(img.getdata())

    pixels = [p for p in pixels if sum(p) > threshold]

    # Count the occurrence of each color
    color_counter = collections.Counter(pixels)

    # Find the most common colors
    dominant_colors = color_counter.most_common(num_colors)

    return [color[0] for color in dominant_colors]


def extract_characteristic_color(img, thumb_size=60, threshold=0):
    img = img.copy()
    img.thumbnail((thumb_size, thumb_size))

    # Calculate the average color of the image
    width, height = img.size
    pixel_data = list(img.getdata())

    threshold *= 3
    total_red = total_green = total_blue = 0
    total_pixels = 0
    for r, g, b, *_ in pixel_data:
        if r + g + b > threshold:
            total_red += r
            total_green += g
            total_blue += b
            total_pixels += 1

    average_color = (total_red // total_pixels, total_green // total_pixels, total_blue // total_pixels)

    return average_color


def draw_text_with_font(text: str, font: ImageFont, text_color=(0, 0, 0, 255), stroke_width=0, stroke_fill=None):
    background_color = (255, 255, 255, 0)  # Transparent background

    # Initialize the drawing context with a temporary image to calculate text size
    text_width, text_height = font_estimate_size(font, text)

    image = Image.new("RGBA", (
        text_width + stroke_width * 2, text_height + stroke_width * 2
    ), background_color)

    # Initialize the drawing context
    draw = ImageDraw.Draw(image)

    # Draw the text on the image
    x = y = stroke_width
    draw.text((x, y), text, fill=text_color, font=font,
              stroke_width=stroke_width,
              stroke_fill=stroke_fill,
              anchor='lt')

    return image


def linear_gradient(target_image: Image, poly, p1, p2, c1, c2):
    """
    Draw polygon with linear gradient from point 1 to point 2 and ranging
    from color 1 to color 2 on given image

    :param target_image: Image to draw on
    :param poly: Polygon to draw [(x1, y1), (x2, y2), ...]
    :param p1: Start point of gradient
    :param p2: End point of gradient
    :param c1: Start color of gradient (R, G, B)
    :param c2: End color of gradient (R, G, B)
    """
    # Draw initial polygon, alpha channel only, on an empty canvas of image size
    ii = Image.new('RGBA', target_image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(ii)
    draw.polygon(poly, fill=(0, 0, 0, 255), outline=None)

    # Calculate angle between point 1 and 2
    p1 = np.array(p1)
    p2 = np.array(p2)
    angle = np.arctan2(p2[1] - p1[1], p2[0] - p1[0]) / np.pi * 180

    # Rotate and crop shape
    temp = ii.rotate(angle, expand=True)
    temp = temp.crop(temp.getbbox())
    wt, ht = temp.size

    w, h = target_image.size
    # Create gradient from color 1 to 2 of appropriate size
    gradient = np.linspace(c1, c2, wt, True).astype(np.uint8)
    gradient = np.tile(gradient, [2 * h, 1, 1])
    gradient = Image.fromarray(gradient)

    # Paste gradient on blank canvas of sufficient size
    temp = Image.new('RGBA', (max(target_image.size[0], gradient.size[0]),
                              max(target_image.size[1], gradient.size[1])), (0, 0, 0, 0))
    temp.paste(gradient)
    gradient = temp

    # Rotate and translate gradient appropriately
    x = np.sin(angle * np.pi / 180) * ht
    y = np.cos(angle * np.pi / 180) * ht
    gradient = gradient.rotate(-angle, center=(0, 0),
                               translate=(p1[0] + x, p1[1] - y))

    # Paste gradient on temporary image
    ii.paste(gradient.crop((0, 0, ii.size[0], ii.size[1])), mask=ii)

    # Paste temporary image on actual image
    target_image.paste(ii, mask=ii)

    return target_image


# Draw polygon with radial gradient from point to the polygon border
# ranging from color 1 to color 2 on given image
def radial_gradient(i, poly, p, c1, c2):
    # Draw initial polygon, alpha channel only, on an empty canvas of image size
    ii = Image.new('RGBA', i.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(ii)
    draw.polygon(poly, fill=(0, 0, 0, 255), outline=None)

    # Use polygon vertex with the highest distance to given point as end of gradient
    p = np.array(p)
    max_dist = max([np.linalg.norm(np.array(v) - p) for v in poly])

    # Calculate color values (gradient) for the whole canvas
    x, y = np.meshgrid(np.arange(i.size[0]), np.arange(i.size[1]))
    c = np.linalg.norm(np.stack((x, y), axis=2) - p, axis=2) / max_dist
    c = np.tile(np.expand_dims(c, axis=2), [1, 1, 3])
    c = (c1 * (1 - c) + c2 * c).astype(np.uint8)
    c = Image.fromarray(c)

    # Paste gradient on temporary image
    ii.paste(c, mask=ii)

    # Paste temporary image on actual image
    i.paste(ii, mask=ii)

    return i
