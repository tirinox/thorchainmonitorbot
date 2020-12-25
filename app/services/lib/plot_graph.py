from datetime import datetime
from io import BytesIO

import pandas as pd
from PIL import Image
from PIL import ImageDraw, ImageFont


def img_to_bio(image, name):
    bio = BytesIO()
    bio.name = name
    image.save(bio, 'PNG')
    bio.seek(0)
    return bio


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


class PlotBarGraph:
    GRADIENT_TOP_COLOR = '#3d5975'
    GRADIENT_BOTTOM_COLOR = '#121a23'
    PLOT_COLOR = '#62d0e3'
    PLOT_COLOR_2 = '#52c0d3'

    BASE = './data'
    FONT_BOLD = f'{BASE}/my.ttf'
    font_ticks = ImageFont.truetype(FONT_BOLD, 15)
    font_title = ImageFont.truetype(FONT_BOLD, 35)

    def __init__(self, w=800, h=600):
        self.w = w
        self.h = h
        self.image = generate_gradient(self.GRADIENT_TOP_COLOR, self.GRADIENT_BOTTOM_COLOR, w, h)
        self.draw = ImageDraw.Draw(self.image)
        self.series = []
        self.x_values = []
        self.margin = 2  # px
        self.left = 60
        self.right = 60
        self.bottom = 60
        self.top = 60
        self.title = ''
        self.min_y = None
        self.max_y = None

    def plot_bars(self, df: pd.DataFrame, column, color):
        values = df[column]

        self.x_values = df.index.values.tolist()
        self.series.append((
            values.values.tolist(), color
        ))

        return self

    def update_bounds_y(self):
        self.min_y = 1e100
        self.max_y = -1e100

        colors = [s[1] for s in self.series]
        y_values = [s[0] for s in self.series]
        for x, *ys in zip(self.x_values, *y_values):
            total_y = sum(ys)
            self.min_y = min(total_y, self.min_y)
            self.max_y = max(total_y, self.max_y)

    def _plot(self):
        n = len(self.x_values)
        if n <= 0:
            return

        colors = [s[1] for s in self.series]
        y_values = [s[0] for s in self.series]

        m = self.margin
        h = self.h - self.bottom - self.top
        w = self.w - self.left - self.right
        block_width = (w - m * (n - 1)) / n
        cur_x = self.left
        for x, *ys in zip(self.x_values, *y_values):
            cur_y = self.bottom
            for y, color in zip(ys, colors):
                height = y / self.max_y * h
                self.draw.rectangle((
                    int(cur_x), self.h - int(cur_y),
                    int(cur_x + block_width), self.h - int(cur_y + height)
                ), fill=color)
                cur_y += height
            cur_x += block_width + m

    def _plot_ticks(self, ticks, axis='x', text_color='#ffffff'):
        if not ticks:
            return
        n_ticks = len(ticks)

        if axis == 'x':
            cur_x = self.left
            cur_y = self.h - self.bottom * 0.7
            width = self.w - self.left - self.right
            x_step = width / (n_ticks - 1)
            y_step = 0
            anchor = 'lm'
        else:
            cur_x = self.left * 0.85
            cur_y = self.h - self.bottom
            height = self.h - self.top - self.bottom
            y_step = -height / (n_ticks - 1)
            x_step = 0
            anchor = 'rm'

        for t in ticks:
            self.draw.text((int(cur_x), int(cur_y)), t, anchor=anchor, fill=text_color,
                           font=self.font_ticks)
            cur_x += x_step
            cur_y += y_step

    def _plot_ticks_time_horizontal(self, n_ticks=11, text_color='#ffffff'):
        n = len(self.x_values)
        if n <= 0:
            return

        min_x = min(self.x_values)
        max_x = max(self.x_values)

        cur_t = min_x
        t_step = (max_x - min_x) / (n_ticks - 1)

        ticks = []
        for i in range(n_ticks):
            seconds = int(cur_t / 1_000_000_000)
            text = datetime.fromtimestamp(seconds).strftime('%H:%M')
            ticks.append(text)
            cur_t += t_step

        self._plot_ticks(ticks, 'x', text_color)

    def _plot_ticks_int_vertical(self, n_ticks=11, text_color='#ffffff'):
        n = len(self.x_values)
        if n <= 0:
            return

        cur_t = self.min_y
        t_step = (self.max_y - self.min_y) / (n_ticks - 1)

        ticks = []
        for i in range(n_ticks):
            ticks.append(str(int(cur_t)))
            cur_t += t_step

        self._plot_ticks(ticks, 'y', text_color)

    def add_title(self, title):
        self.title = title
        return self

    def _draw_title(self):
        x = int(self.w * 0.5)
        y = int(self.top * 0.5)
        self.draw.text((x, y), self.title, 'white', self.font_title, anchor='mm')

    def finalize(self, name='plot.png'):
        if self.max_y is None:
            self.update_bounds_y()
        self._plot()
        self._plot_ticks_time_horizontal()
        self._plot_ticks_int_vertical()
        if self.title:
            self._draw_title()
        return img_to_bio(self.image, name)
