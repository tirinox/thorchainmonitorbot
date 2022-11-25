import abc
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
        return f'{self.FILENAME_PREFIX}{today_str()}.png'

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
            (self.x, self.y),
            (self.x2, self.y2)
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


class PackItem(NamedTuple):
    label: str
    weight: float = 1
    color: str = TC_WHITE
    meta_data: str = ''


class DrawRectPacker:
    V = 'vert'
    H = 'hor'

    def __init__(self, items=None):
        self.items: List[PackItem] = items or []

    def append(self, label, weight, color):
        self.items.append(PackItem(label, weight, color))

    @property
    def total_weight(self):
        return sum(item.weight for item in self.items)

    def pack(self, into: Rect, align=V) -> List[Tuple[PackItem, Rect]]:
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
