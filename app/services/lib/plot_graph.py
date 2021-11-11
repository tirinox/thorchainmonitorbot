from datetime import datetime

import pandas as pd
from PIL import Image
from PIL import ImageDraw, ImageFont

from services.lib.draw_utils import generate_gradient, LIGHT_TEXT_COLOR


class PlotGraph:
    GRADIENT_TOP_COLOR = '#3d5975'
    GRADIENT_BOTTOM_COLOR = '#121a23'
    PLOT_COLOR = '#62d0e3'
    PLOT_COLOR_2 = '#52c0d3'
    TICK_COLOR = '#555577'

    BASE = './data'
    FONT_BOLD = f'{BASE}/my.ttf'

    def __init__(self, w=800, h=600, bg='gradient'):
        self.w = w
        self.h = h
        if bg == 'gradient':
            self.image = generate_gradient(self.GRADIENT_TOP_COLOR, self.GRADIENT_BOTTOM_COLOR, w, h)
        else:
            self.image = Image.new('RGBA', (w, h), bg)
        self.draw = ImageDraw.Draw(self.image)
        self.margin = 2  # px
        self.left = 60
        self.right = 60
        self.bottom = 60
        self.top = 60
        self.title = ''
        self.min_y = None
        self.max_y = None
        self.x_formatter = self.time_formatter
        self.y_formatter = self.int_formatter
        self.n_ticks_x = 11
        self.n_ticks_y = 20
        self.font_ticks = ImageFont.truetype(self.FONT_BOLD, 15)
        self.font_title = ImageFont.truetype(self.FONT_BOLD, 35)
        self.tick_size = 4
        self.axis_text_color = '#ffffff'
        self.grid_lines = False
        self.tick_color = self.TICK_COLOR

    def plot_rect(self):
        width = self.w - self.left - self.right
        height = self.h - self.top - self.bottom
        return self.left, self.h - self.bottom, width, height

    def _plot_ticks(self, ticks, axis='x'):
        if not ticks:
            return
        n_ticks = len(ticks)

        ox, oy, width, height = self.plot_rect()

        if axis == 'x':
            cur_x = self.left
            cur_y = self.h - self.bottom * 0.7
            x_step = width / (n_ticks - 1)
            y_step = 0
            anchor = 'mm'
            self.draw.line((int(ox), int(oy),
                            int(self.left + width), int(self.h - self.bottom)),
                           self.tick_color, width=1)
        else:
            cur_x = self.left * 0.8
            cur_y = self.h - self.bottom
            y_step = -height / (n_ticks - 1)
            x_step = 0
            anchor = 'rm'
            self.draw.line((int(ox), int(cur_y),
                            int(ox), int(self.top)),
                           self.tick_color, width=1)

        for t in ticks:
            x, y = int(cur_x), int(cur_y)
            self.draw.text((x, y), t, anchor=anchor, fill=self.axis_text_color,
                           font=self.font_ticks)
            if axis == 'y':
                left = self.left + width if self.grid_lines else self.left
                self.draw.line((left, y, self.left - self.tick_size, y), self.tick_color, width=1)
            else:
                top = self.top if self.grid_lines else self.h - self.bottom
                self.draw.line((x, top, x, self.h - self.bottom + self.tick_size),
                               self.tick_color, width=1)
            cur_x += x_step
            cur_y += y_step

    @staticmethod
    def time_formatter(timestamp):
        return datetime.fromtimestamp(timestamp).strftime('%H:%M')

    @staticmethod
    def int_formatter(y):
        return str(int(y))

    @staticmethod
    def date_formatter(t):
        return datetime.fromtimestamp(t).strftime('%b %d')

    def add_title(self, title):
        self.title = title
        return self

    def _draw_title(self):
        x = int(self.w * 0.5)
        y = int(self.top * 0.5)
        self.draw.text((x, y), self.title, LIGHT_TEXT_COLOR, self.font_title, anchor='mm')

    def _plot(self):  # abstract
        ...

    def finalize(self):
        self._plot()
        if self.title:
            self._draw_title()
        return self.image


class PlotBarGraph(PlotGraph):
    def __init__(self, w=800, h=600, bg='gradient'):
        super().__init__(w, h, bg)
        self.series = []
        self.x_values = []

    def plot_bars(self, df: pd.DataFrame, column, color):
        values = df[column]

        self.x_values = [int(cur_t / 1_000_000_000) for cur_t in df.index.values.tolist()]
        self.series.append((
            values.values.tolist(), color
        ))

        return self

    def plot_arrays(self, colors, dates, list_of_series):
        self.x_values = dates
        for series, color in zip(list_of_series, colors):
            self.series.append((list(series), color))

    def update_bounds_y(self):
        self.min_y = 1e100
        self.max_y = -1e100

        y_values = [s[0] for s in self.series]
        for x, *ys in zip(self.x_values, *y_values):
            total_y = sum(ys)
            self.min_y = min(total_y, self.min_y)
            self.max_y = max(total_y, self.max_y)

    def _plot(self):
        n = len(self.x_values)
        if n <= 0:
            return

        if self.max_y is None:
            self.update_bounds_y()

        self._plot_ticks_time_horizontal()
        self._plot_ticks_int_vertical()

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

    def _plot_ticks_time_horizontal(self):
        n_ticks = self.n_ticks_x
        n = len(self.x_values)
        if n <= 0:
            return

        min_x = min(self.x_values)
        max_x = max(self.x_values)

        cur_t = min_x
        t_step = (max_x - min_x) / (n_ticks - 1)

        ticks = []
        for i in range(n_ticks):
            text = self.x_formatter(cur_t)
            ticks.append(text)
            cur_t += t_step

        self._plot_ticks(ticks, 'x')

    def _plot_ticks_int_vertical(self):
        n_ticks = self.n_ticks_y
        n = len(self.x_values)
        if n <= 0:
            return

        cur_t = self.min_y
        t_step = (self.max_y - self.min_y) / (n_ticks - 1)

        ticks = []
        for i in range(n_ticks):
            ticks.append(self.y_formatter(cur_t))
            cur_t += t_step

        self._plot_ticks(ticks, 'y')


class PlotGraphLines(PlotGraph):
    def __init__(self, w=800, h=600, bg='gradient'):
        super().__init__(w, h, bg)
        self.series = []
        self.min_x = self.max_x = 0.0
        self.line_width = 3
        self.legend_x = self.left
        self.legend_y = self.h - self.bottom * 0.5
        self.show_min_max = False

    def update_bounds(self):
        self.min_x = self.min_y = 1e10
        self.max_x = self.max_y = -1e10
        for line_desc in self.series:
            points = line_desc['pts']
            for x, y in points:
                self.min_x = min(self.min_x, x)
                self.min_y = min(self.min_y, y)
                self.max_x = max(self.max_x, x)
                self.max_y = max(self.max_y, y)

    def add_series(self, list_of_points, color):
        self.series.append({
            'pts': list_of_points,
            'color': color
        })

    def _plot_ticks_axis(self, v_min, v_max, axis, n_ticks):
        if v_min >= v_max:
            return

        cur_v = v_min
        t_step = (v_max - v_min) / (n_ticks - 1)

        formatter = self.x_formatter if axis == 'x' else self.y_formatter
        ticks = []
        for i in range(n_ticks):
            text = formatter(cur_v)
            ticks.append(text)
            cur_v += t_step

        self._plot_ticks(ticks, axis)

    def convert_coords(self, x, y, ox, oy, w, h):
        norm_x, norm_y = (
            (x - self.min_x) / (self.max_x - self.min_x),
            (y - self.min_y) / (self.max_y - self.min_y),
        )
        return int(ox + norm_x * w), int(oy - norm_y * h)

    def add_legend(self, color, title):
        tw, th = self.font_ticks.getsize(title)
        half_square_sz = 5
        self.draw.rectangle(
            (
                self.legend_x - half_square_sz,
                self.legend_y - half_square_sz,
                self.legend_x + half_square_sz,
                self.legend_y + half_square_sz
            ),
            fill=color
        )
        self.legend_x += 20
        self.draw.text((self.legend_x - half_square_sz, self.legend_y),
                       title, fill='#fff', font=self.font_ticks, anchor='lm')
        self.legend_x += tw + 20

    def _plot(self):
        # if self.max_y <= self.min_y or self.max_x <= self.max_y:

        self._plot_ticks_axis(self.min_x, self.max_x, 'x', self.n_ticks_x)
        self._plot_ticks_axis(self.min_y, self.max_y, 'y', self.n_ticks_y)

        ox, oy, plot_w, plot_h = self.plot_rect()

        for line_desc in self.series:
            points = line_desc['pts']
            if not points:
                continue

            color = line_desc['color']

            x0, y0 = points[0]
            last_x, last_y = self.convert_coords(x0, y0, ox, oy, plot_w, plot_h)
            for x, y in points[1:]:
                cur_x, cur_y = self.convert_coords(x, y, ox, oy, plot_w, plot_h)
                self.draw.line((last_x, last_y, cur_x, cur_y), fill=color, width=self.line_width)
                last_x, last_y = cur_x, cur_y

        if self.show_min_max:
            self._print_min_max()

    def _print_min_max(self):
        ox, oy, plot_w, plot_h = self.plot_rect()

        for line_desc in self.series:
            points = line_desc['pts']
            if not points:
                continue

            min_x = max_x = points[0][0]
            min_y = max_y = points[0][1]
            for x, y in points[1:]:
                if y < min_y:
                    min_x, min_y = x, y
                if y > max_y:
                    max_x, max_y = x, y

            # print(f'{min_x = }, {min_y = }, {max_x = }, {max_y = }')

            min_px, min_py = self.convert_coords(min_x, min_y, ox, oy, plot_w, plot_h)
            max_px, max_py = self.convert_coords(max_x, max_y, ox, oy, plot_w, plot_h)
            color = line_desc['color']

            self.draw.text((min_px + 6, min_py + 10), self.y_formatter(float(min_y)), color, self.font_ticks,
                           anchor='mm')
            self.draw.text((max_px + 6, max_py - 10), self.y_formatter(float(max_y)), color, self.font_ticks,
                           anchor='mm')
