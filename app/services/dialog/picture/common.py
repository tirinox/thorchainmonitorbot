import abc
import math
from typing import Tuple, NamedTuple, List, Optional

import PIL.Image

from localization.manager import BaseLocalization
from services.lib.date_utils import today_str
from services.lib.draw_utils import TC_WHITE
from services.lib.utils import async_wrap, WithLogger

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
        return None


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


class PackItem(NamedTuple):
    label: str
    weight: float = 1
    color: str = TC_WHITE
    meta_data: dict = None

    def meta_key(self, key):
        return self.meta_data.get(key) if self.meta_data else None


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

    def _pack_inside_largest(self, into: Rect):
        if not self.items:
            return []

        sorted_items = list(sorted(self.items, key=lambda i: i.weight, reverse=True))

        total_s = into.w * into.h
        total_m = self.total_weight
        ratio = into.w / into.h

        yield sorted_items[0], into

        margin = 0

        x = into.x + into.w - margin
        for item in sorted_items[1:]:
            hi = math.sqrt(total_s * item.weight / (total_m * ratio))
            wi = hi * ratio
            y = into.y + into.h - hi - margin
            yield item, Rect(
                x - wi, y, wi, hi
            )
            x -= wi

    def pack(self, into: Rect, align=V) -> List[Tuple[PackItem, Rect]]:
        if align in (self.V, self.H):
            return list(self._pack_linear(into, align))
        else:
            return list(self._pack_inside_largest(into))
