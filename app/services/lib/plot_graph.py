from datetime import datetime
from typing import List

import pandas as pd
from PIL import Image
from PIL import ImageDraw, ImageFont

from services.dialog.picture.resources import Resources
from services.lib.draw_utils import LIGHT_TEXT_COLOR, default_gradient, get_palette_color_by_index, TC_WHITE, \
    font_estimate_size

BIG_NUMBER = 1e20


class PlotGraph:
    PLOT_COLOR = '#62d0e3'
    PLOT_COLOR_2 = '#52c0d3'
    TICK_COLOR = '#555577'

    def __init__(self, w=800, h=600, bg='gradient'):
        self.w = w
        self.h = h
        if bg == 'gradient':
            self.image = default_gradient(w, h)
        else:
            if bg is None:
                bg = (0, 0, 0, 0)
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

        r = Resources()
        self.font_ticks = r.fonts.get_font(15)
        self.font_title = r.fonts.get_font_bold(35)
        self.tick_size = 4
        self.axis_text_color = TC_WHITE
        self.grid_lines = False
        self.tick_color = self.TICK_COLOR

    def plot_rect(self):
        width = self.w - self.left - self.right
        height = self.h - self.top - self.bottom
        return self.left, self.h - self.bottom, width, height

    def _plot_ticks(self, ticks, axis='xy?'):
        if not ticks:
            return
        n_ticks = len(ticks)

        ox, oy, width, height = self.plot_rect()

        if axis == 'x':
            cur_x = self.left
            cur_y = self.h - self.bottom + 10
            x_step = width / (n_ticks - 1)
            y_step = 0
            anchor = 'mt'
            self.draw.line((int(ox), int(oy),
                            int(self.left + width), int(self.h - self.bottom)),
                           self.tick_color, width=1)
        else:
            cur_x = self.left - 10
            cur_y = self.h - self.bottom
            y_step = -height / (n_ticks - 1)
            x_step = 0
            anchor = 'rb'
            self.draw.line((int(ox), int(cur_y),
                            int(ox), int(self.top)),
                           self.tick_color, width=1)

        for i, t in enumerate(ticks):
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

    def plot_legend_unit(self, legend_x, legend_y, color, title, font=None):
        font = font or self.font_ticks
        half_square_sz = 7
        self.draw.rectangle(
            (
                legend_x - half_square_sz,
                legend_y - half_square_sz,
                legend_x + half_square_sz,
                legend_y + half_square_sz
            ),
            fill=color, outline='black'
        )
        self.draw.text((legend_x + 20 - half_square_sz, legend_y),
                       title, fill=TC_WHITE, font=font, anchor='lm')

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
        self.min_y = BIG_NUMBER
        self.max_y = -BIG_NUMBER

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

        max_y = self.max_y if self.max_y else 1.0

        for x, *ys in zip(self.x_values, *y_values):
            cur_y = self.bottom
            for y, color in zip(ys, colors):
                height = y / max_y * h
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

        self.font_bars = None

        self.bar_series = []
        self.bar_height_limit = 144

        self.bar_max = -BIG_NUMBER
        self.bar_min = BIG_NUMBER

    def update_line_bounds(self):
        self.min_x = self.min_y = BIG_NUMBER
        self.max_x = self.max_y = -BIG_NUMBER
        for line_desc in self.series:
            points = line_desc['pts']
            for x, y in points:
                self.min_x = min(self.min_x, x)
                self.min_y = min(self.min_y, y)
                self.max_x = max(self.max_x, x)
                self.max_y = max(self.max_y, y)

    def update_bar_bounds(self):
        self.bar_max = -BIG_NUMBER
        self.bar_min = BIG_NUMBER

        for line_desc in self.bar_series:
            points = line_desc['pts']
            for x, y in points:
                self.min_x = min(self.min_x, x)
                self.max_x = max(self.max_x, x)
                self.bar_max = max(self.bar_max, y)
                self.bar_min = min(self.bar_min, y)

    def update_bounds(self):
        self.update_line_bounds()
        self.update_bar_bounds()

    def add_series(self, list_of_points, color):
        self.series.append({
            'pts': list_of_points,
            'color': color
        })

    def add_series_bars(self, list_of_points, color, thickness=10, x_shift=0, show_values=0):
        self.bar_series.append({
            'pts': list_of_points,
            'color': color,
            'thickness': thickness,
            'x_shift': x_shift,
            'show_values': show_values,
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
        tw, th = font_estimate_size(self.font_ticks, title)

        self.plot_legend_unit(self.legend_x, self.legend_y, color, title)
        self.legend_x += tw + 40

    def _plot(self):
        if self.min_y == self.max_y or self.min_x == self.max_x:
            return

        self._plot_ticks_axis(self.min_x, self.max_x, 'x', self.n_ticks_x)
        self._plot_ticks_axis(self.min_y, self.max_y, 'y', self.n_ticks_y)

        self._plot_bars()

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

    BAR_LABEL_MODE_ON_CHANGE = 'on_change'
    BAR_LABEL_MODE_MIN_MAX = 'min_max'

    def _plot_bars(self):
        ox, oy, plot_w, plot_h = self.plot_rect()

        bar_div = max(abs(self.bar_min), abs(self.bar_max))
        if bar_div == 0:  # hot fix
            return

        font_value = self.font_bars or self.font_ticks

        bar_normal_height = self.bar_height_limit / bar_div

        for line_desc in self.bar_series:
            points = line_desc['pts']
            if not points:
                continue

            color = line_desc['color']
            bh2 = line_desc['thickness'] * 0.5
            x_shift = line_desc['x_shift']
            show_values = line_desc['show_values']

            min_y = min(p[1] for p in points)
            max_y = max(p[1] for p in points)
            min_y_shown, max_y_shown = False, False

            last_value = None
            for i, (x, y) in enumerate(points):
                x, _ = self.convert_coords(x, y, ox, oy, plot_w, plot_h)

                bar_height = bar_normal_height * y

                if bar_height > 0.1:
                    self.draw.rectangle((
                        int(x - bh2 + x_shift), int(oy - bar_height),
                        int(x + bh2 + x_shift), int(oy),
                    ), fill=color)

                if show_values:
                    do_it = False
                    if show_values == self.BAR_LABEL_MODE_ON_CHANGE:
                        if last_value and y != last_value:
                            do_it = True
                    elif show_values == self.BAR_LABEL_MODE_MIN_MAX:
                        if y == min_y and not min_y_shown:
                            do_it = True
                            min_y_shown = True
                        elif y == max_y and not max_y_shown:
                            do_it = True
                            max_y_shown = True
                    elif i % show_values == 0:
                        do_it = True
                    if do_it:
                        self.draw.text(
                            (int(x + x_shift), int(oy - bar_height - 10)),
                            str(y),
                            anchor='ms',
                            fill=color,
                            font=font_value,
                        )
                last_value = y


def plot_legend(draw: ImageDraw, elements: List[str], xy,
                font: ImageFont,
                sq_size=0, x_step=14, y_step=0,
                max_width=1000,
                label_shift_x=5, is_circle=True,
                label_color='auto',
                palette=get_palette_color_by_index):
    current_x, current_y = x, y = xy

    brush = draw.ellipse if is_circle else draw.rectangle

    for i, label in enumerate(elements):
        w, h = font_estimate_size(font, label)

        y_step = y_step or int(h * 1.24)
        sq_size = sq_size or h

        full_item_width = w + label_shift_x + sq_size + x_step

        if current_x - x + full_item_width > max_width:
            current_x = x
            current_y += y_step

        color = palette(i)

        brush((
            (current_x, current_y),
            (current_x + sq_size, current_y + sq_size)
        ), fill=color)
        final_text_color = color if label_color == 'auto' else label_color
        draw.text((current_x + sq_size + label_shift_x, current_y + sq_size // 2),
                  label, final_text_color, font=font, anchor='lm', )

        current_x += full_item_width
