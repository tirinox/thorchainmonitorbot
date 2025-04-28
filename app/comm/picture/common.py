import abc
import math
from typing import Tuple, NamedTuple, List, Optional

import PIL.Image

from comm.localization.manager import BaseLocalization
from lib.date_utils import today_str
from lib.draw_utils import TC_WHITE, font_estimate_size, result_color
from lib.logs import WithLogger
from lib.money import calc_percent_change, short_money
from lib.texts import bracketify
from lib.utils import async_wrap

PictureAndName = Tuple[Optional[PIL.Image.Image], str]


class BasePictureGenerator(WithLogger, abc.ABC):
    WIDTH = 1024
    HEIGHT = 768
    FILENAME_PREFIX = 'some_picture'

    def __init__(self, loc: BaseLocalization):
        super().__init__()
        self.loc = loc

    async def prepare(self):
        ...

    async def get_picture(self) -> PictureAndName:
        try:
            self.logger.info('Started building a picture...')
            await self.prepare()
            pic = await self._get_picture_sync()
            return pic, self.generate_picture_filename()
        except Exception:
            self.logger.exception('An error occurred when generating a picture!', exc_info=True)
            return None, ""

    def generate_picture_filename(self):
        return f'{self.FILENAME_PREFIX}-{today_str()}.png'

    @async_wrap
    def _get_picture_sync(self):
        raise NotImplementedError

    @classmethod
    def text_and_change(cls, old_v, new_v, draw, x, y, text, font_main, font_second, fill='#fff',
                        x_shift=20, y_shift=6, right_of_text=True):
        size_x = 0
        if text:
            draw.text((x, y), text, font=font_main, fill=fill, anchor='lm')
            if right_of_text:
                size_x, _ = font_estimate_size(font_main, text)

        cls.draw_text_change(old_v, new_v, draw,
                             x=x + size_x + x_shift, y=y + y_shift,
                             font=font_second)

    @staticmethod
    def draw_text_change(old_v, new_v, draw, x, y, font, min_change_pct=0.1, anchor='lm'):
        percent = calc_percent_change(old_v, new_v)
        if abs(percent) > min_change_pct:
            draw.text(
                (int(x), int(y)),
                bracketify(short_money(percent, postfix='%', signed=True)),
                anchor=anchor, fill=result_color(percent), font=font
            )


class Rect(NamedTuple):
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0

    @classmethod
    def from_frame(cls, left, top, right, bottom, width, height):
        return cls(
            left, top,
            width - left - right,
            height - top - bottom
        )

    @property
    def x2(self):
        return self.x + self.w

    @property
    def y2(self):
        return self.y + self.h

    @property
    def int_rect(self):
        return Rect(
            int(self.x), int(self.y),
            int(self.w), int(self.h)
        )

    @property
    def coordinates(self):
        return (
            (min(self.x, self.x2), min(self.y, self.y2)),
            (max(self.x, self.x2), max(self.y, self.y2))
        )

    @property
    def center(self):
        return (
            self.x + self.w * 0.5,
            self.y + self.h * 0.5
        )

    def shift_from_origin(self, px, py):
        return (
            self.x + px,
            self.y + py
        )

    def extend(self, a):
        return Rect(
            self.x - a,
            self.y - a,
            max(1, self.w + a * 2),
            max(1, self.h + a * 2)
        )

    def anchored_position(self, anchor, extra_x=0, extra_y=0):
        if anchor == 'center':
            x, y = self.center
        elif anchor == 'top':
            x, y = self.center[0], self.y
        elif anchor == 'bottom':
            x, y = self.center[0], self.y2
        else:
            raise ValueError(f'Unknown anchor: {anchor}')
        return x + extra_x, y + extra_y


class PackItem(NamedTuple):
    label: str
    weight: float = 1
    color: str = TC_WHITE
    meta_data: dict = None

    def meta_key(self, key, default=None):
        return self.meta_data.get(key, default) if self.meta_data else default


class DrawRectPacker:
    V = 'vert'
    H = 'hor'
    INSIDE_LARGEST = 'inside_largest'

    def __init__(self, items=None):
        self.items: List[PackItem] = items or []

    def append(self, label, weight, color):
        self.items.append(PackItem(label, weight, color))

    @property
    def total_weight(self):
        return sum(item.weight for item in self.items)

    def _pack_linear(self, into: Rect, align=V):
        horizontal = align == self.H
        full_size = into.w if horizontal else into.h
        x, y = into.x, into.y

        total_weight = self.total_weight
        if not total_weight:
            return []

        for item in self.items:
            advance = item.weight / total_weight * full_size

            yield item, Rect(
                x, y,
                advance if horizontal else into.w,
                into.h if horizontal else advance
            )

            if horizontal:
                x += advance
            else:
                y += advance

    def _pack_inside_largest(self, into: Rect, left=True):
        if not self.items:
            return []

        sorted_items = list(sorted(self.items, key=lambda i: i.weight, reverse=True))

        total_s = into.w * into.h
        total_m = self.total_weight
        ratio = into.w / into.h

        yield sorted_items[0], into

        margin = 0

        x = into.x if left else into.x + into.w - margin
        for item in sorted_items[1:]:
            hi = math.sqrt(total_s * item.weight / (total_m * ratio))
            wi = hi * ratio
            y = into.y + into.h - hi - margin
            yield item, Rect(
                x if left else x - wi,
                y, wi, hi
            )
            if left:
                x += wi
            else:
                x -= wi

    def pack(self, into: Rect, align=V) -> List[Tuple[PackItem, Rect]]:
        if align in (self.V, self.H):
            return list(self._pack_linear(into, align))
        else:
            return list(self._pack_inside_largest(into))
