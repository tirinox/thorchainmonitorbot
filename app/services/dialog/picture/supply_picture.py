from typing import List, NamedTuple, Tuple

from localization.base import BaseLocalization
from services.dialog.picture.resources import Resources
from services.jobs.fetch.circulating import RuneCirculatingSupply
from services.lib.date_utils import today_str
from services.lib.draw_utils import img_to_bio
from services.lib.plot_graph import PlotGraph
from services.lib.utils import async_wrap, vertical_text, WithLogger
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

    def shift_from_origin(self, px, py):
        return (
            self.x + px,
            self.y + py
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


class SupplyBlock(NamedTuple):
    label: str = ''
    alignment: str = DrawRectPacker.H
    weight: float = 1.0
    children: List['SupplyBlock'] = None


class SupplyPictureGenerator(WithLogger):
    WIDTH = 1024
    HEIGHT = 768

    CHART_TEXT_COLOR = 'white'

    PALETTE = {
        'Circulating': '#34d5d0',
        'ERC20': '#ecf0f1',
        'BEP2': '#FFD700',
        'Team': '#b9d4e9',
        'Seed': '#9ac4e4',
        'Reserves': '#5179b8',
        'Undeployed reserves': '#382d80',
        'Killed': '#F22222',
    }

    def _draw_rect(self, r: Rect, color, label='', outline='black'):
        if color:
            self.gr.draw.rectangle(r.coordinates, color, outline=outline)
        if label:
            self._add_text(r.shift_from_origin(5, 5), label)

    def _add_text(self, xy, text):
        self.gr.draw.text(xy, text, fill='white', font=self.gr.font_ticks, stroke_width=1,
                          stroke_fill='black')

    def __init__(self, loc: BaseLocalization, supply: RuneCirculatingSupply, killed_rune: KilledRuneEntry):
        super().__init__()
        self.supply = supply
        self.killed = killed_rune
        self.loc = loc
        self.font = Resources().font_small
        self.gr = PlotGraph(self.WIDTH, self.HEIGHT)
        self.locked_thor_rune = supply.thor_rune.locked_amount
        self.translate = {
            'Circulating': self.loc.SUPPLY_PIC_CIRCULATING,
            'Team': self.loc.SUPPLY_PIC_TEAM,
            'Seed': self.loc.SUPPLY_PIC_SEED,
            'Reserves': self.loc.SUPPLY_PIC_RESERVES,
            'Undeployed reserves': self.loc.SUPPLY_PIC_UNDEPLOYED,
            'Killed': self.loc.SUPPLY_PIC_KILLED,
        }

    async def get_picture(self):
        try:
            self.logger.info('Started buinding a picture...')
            return await self._get_picture_sync()
        except Exception:
            self.logger.exception('An error occurred when generating a picture!', exc_info=True)

    @async_wrap
    def _get_picture_sync(self):
        today = today_str()

        self.gr.title = self.loc.SUPPLY_PIC_TITLE
        self.gr.top = 80
        self._plot()
        self._add_legend()

        return img_to_bio(self.gr.finalize(), f'thorchain_supply_{today}.png')

    def _add_legend(self):
        x = 55
        y = self.HEIGHT - 50
        for title, color in self.PALETTE.items():
            title = self.translate.get(title, title)
            dx, _ = self.gr.font_ticks.getsize(title)
            self.gr.plot_legend_unit(x, y, color, title)
            x += dx + 40

    def _pack(self, items, outer_rect, align):
        packer = DrawRectPacker(items)
        results = list(packer.pack(outer_rect, align))
        for item, r in results:
            self._draw_rect(r, item.color, item.label)
        return results

    @staticmethod
    def _fit_smaller_rect(outer_rect: Rect, outer_weight, inner_weight) -> Rect:
        # anchor = left-bottom
        alpha = inner_weight / outer_weight
        f = (1.0 - 1.0 / (alpha + 1.0)) ** 0.5
        inner_width = outer_rect.w * f
        inner_height = outer_rect.h * f
        return Rect(
            outer_rect.x,
            outer_rect.y + outer_rect.h - inner_height,
            inner_width,
            inner_height
        )

    def _plot(self):
        outer_rect = Rect.from_frame(50, 80, 50, 80, self.WIDTH, self.HEIGHT)

        bep2_full = self.supply.bep2_rune.circulating
        erc20_full = self.supply.erc20_rune.circulating
        old_full = bep2_full + erc20_full

        ((locked_item, locked_rect), (circ_item, circ_rect), (old_item, old_rect)) = self._pack([
            PackItem('', self.supply.thor_rune.locked_amount, ''),
            PackItem(self.loc.SUPPLY_PIC_CIRCULATING, self.supply.thor_rune.circulating, self.PALETTE['Circulating']),
            PackItem('', old_full, '')
        ], outer_rect, align=DrawRectPacker.H)

        self._pack([
            PackItem(self.translate.get(lock_type, lock_type), amount, self.PALETTE.get(lock_type, 'black'))
            for lock_type, amount in self.supply.thor_rune.locked.items()
        ], locked_rect, align=DrawRectPacker.V)

        ((erc20_item, erc20_rect), (bep2_item, bep2_rect)) = self._pack([
            PackItem(vertical_text('ERC20'), erc20_full, self.PALETTE['ERC20']),
            PackItem(vertical_text('BEP2'), bep2_full, self.PALETTE['BEP2']),
        ], old_rect, align=DrawRectPacker.V)

        thor_killed = self.killed.killed_switched
        bep2_killed = self.killed.total_killed * bep2_full / old_full
        erc20_killed = self.killed.total_killed * erc20_full / old_full

        killed_color = self.PALETTE['Killed']

        self._pack([
            PackItem('', bep2_full - bep2_killed, ''),
            PackItem('', bep2_killed, killed_color),
        ], bep2_rect, align=DrawRectPacker.V)

        self._pack([
            PackItem('', erc20_full - erc20_killed, ''),
            PackItem('', erc20_killed, killed_color),
        ], erc20_rect, align=DrawRectPacker.V)

        thor_killed_rect = self._fit_smaller_rect(circ_rect, self.supply.thor_rune.circulating,
                                                  (thor_killed + self.supply.lost_forever))

        self._draw_rect(thor_killed_rect, killed_color)
        self._add_text((thor_killed_rect.x2 + 5, thor_killed_rect.y), self.loc.SUPPLY_PIC_KILLED_LOST)
