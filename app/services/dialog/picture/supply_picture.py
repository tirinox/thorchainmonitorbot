from typing import List, NamedTuple, Tuple

from PIL import ImageDraw

from localization.base import BaseLocalization
from services.jobs.fetch.circulating import RuneCirculatingSupply
from services.lib.date_utils import today_str
from services.lib.draw_utils import img_to_bio
from services.lib.plot_graph import PlotGraph
from services.lib.utils import async_wrap
from services.models.killed_rune import KilledRuneEntry


class Rect(NamedTuple):
    x: float
    y: float
    w: float
    h: float

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


class PackItem(NamedTuple):
    label: str = ''
    weight: float = 1
    color: str = '#FFFFFF'


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


class SupplyPictureGenerator:
    WIDTH = 1024
    HEIGHT = 768

    PALETTE = {
        'killed': '#B22222',
        'circulating': '#00FF7F',

    }

    @staticmethod
    def _draw_rect(draw: ImageDraw.ImageDraw, r: Rect, color, label=''):
        draw.rectangle(r.coordinates, color)
        if label:
            draw.text(r.center, label, fill='white', align='middle')

    def __init__(self, loc: BaseLocalization, supply: RuneCirculatingSupply, killed_rune: KilledRuneEntry):
        self.supply = supply
        self.killed = killed_rune
        self.loc = loc

    async def get_picture(self):
        return await self._get_picture_sync()

    @async_wrap
    def _get_picture_sync(self):
        today = today_str()
        gr = PlotGraph(self.WIDTH, self.HEIGHT)

        outer_rect = Rect.from_frame(50, 100, 50, 50, self.WIDTH, self.HEIGHT)

        packer = DrawRectPacker([
            PackItem('Left', 100, 'red'),
            PackItem('Middle', 50, '#ffaa00'),
            PackItem('Right', 80, '#aaff11')
        ])

        for item, r in packer.pack(outer_rect, align=packer.V):
            self._draw_rect(gr.draw, r, item.color, item.label)

        gr.title = 'THORChain Rune supply'  # todo: loc

        return img_to_bio(gr.finalize(), f'thorchain_supply_{today}.png')
