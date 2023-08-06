from typing import List, NamedTuple

from localization.eng_base import BaseLocalization
from services.dialog.picture.common import BasePictureGenerator, DrawRectPacker, Rect, PackItem
from services.dialog.picture.resources import Resources
from services.jobs.fetch.circulating import RuneCirculatingSupply, ThorRealms
from services.lib.money import short_money
from services.lib.plot_graph import PlotGraph
from services.lib.utils import async_wrap
from services.models.net_stats import NetworkStats


class SupplyBlock(NamedTuple):
    label: str = ''
    alignment: str = DrawRectPacker.H
    weight: float = 1.0
    children: List['SupplyBlock'] = None


class SupplyPictureGenerator(BasePictureGenerator):
    WIDTH = 1024
    HEIGHT = 768
    MIN_AMOUNT_FOR_LABEL = 1.5e6

    CHART_TEXT_COLOR = 'white'

    FILENAME_PREFIX = 'thorchain_supply'

    def _draw_rect(self, r: Rect, item: PackItem, outline='black'):
        if item.color:
            self.gr.draw.rectangle(r.coordinates, item.color, outline=outline)
        if item.label:
            self._add_text(r.shift_from_origin(10, 8), item.label)
        meta = item.meta_data
        if meta:
            font = self.res.fonts.get_font(20) if item.weight < 6e6 else self.res.fonts.get_font(34)
            text = short_money(item.weight)

            self._add_text(r.center, text,
                           anchor='mm',
                           font=font,
                           fill=item.color or 'white')

    def _add_text(self, xy, text, fill='white', stroke_fill='black', stroke_width=1, anchor=None, font=None):
        self.gr.draw.text(xy, text,
                          fill=fill,
                          font=font or self.gr.font_ticks,
                          stroke_width=stroke_width,
                          stroke_fill=stroke_fill,
                          anchor=anchor)

    def __init__(self, loc: BaseLocalization,
                 supply: RuneCirculatingSupply,
                 net_stats: NetworkStats):
        super().__init__(loc)

        self.supply = supply
        self.net_stats = net_stats

        self.res = Resources()

        self.font = self.res.font_small

        self.gr = PlotGraph(self.WIDTH, self.HEIGHT)
        self.locked_thor_rune = supply.thor_rune.locked_amount
        self.translate = {
            ThorRealms.CIRCULATING: self.loc.SUPPLY_PIC_CIRCULATING,
            ThorRealms.TEAM: self.loc.SUPPLY_PIC_TEAM,
            ThorRealms.SEED: self.loc.SUPPLY_PIC_SEED,
            ThorRealms.VESTING_9R: self.loc.SUPPLY_PIC_VESTING_9R,
            ThorRealms.RESERVES: self.loc.SUPPLY_PIC_RESERVES,
            ThorRealms.UNDEPLOYED_RESERVES: self.loc.SUPPLY_PIC_UNDEPLOYED,
            ThorRealms.BONDED: self.loc.SUPPLY_PIC_BONDED,
            ThorRealms.POOLED: self.loc.SUPPLY_PIC_POOLED,
        }

        self.PALETTE = {
            ThorRealms.TEAM: '#2ecc71',
            ThorRealms.SEED: '#16a085',
            ThorRealms.VESTING_9R: '#5522e0',
            ThorRealms.RESERVES: '#2980b9',
            ThorRealms.UNDEPLOYED_RESERVES: '#517496',
            ThorRealms.BONDED: '#e67e22',
            ThorRealms.POOLED: '#f39c12',
            ThorRealms.CIRCULATING: '#f8e287',
        }
        self.locked_rect = Rect()
        self.circulating_rect = Rect()
        self.old_rect = Rect()

    @async_wrap
    def _get_picture_sync(self):
        self.gr.title = self.loc.SUPPLY_PIC_TITLE
        self.gr.top = 80
        self._plot()
        self._add_legend()

        return self.gr.finalize()

    def _add_legend(self):
        x = 55
        y = self.HEIGHT - 55
        for title, color in self.PALETTE.items():
            title = self.translate.get(title, title)
            dx, _ = self.gr.font_ticks.getsize(title)
            self.gr.plot_legend_unit(x, y, color, title)
            x += dx + 40
            if x >= self.WIDTH - 100:
                x = 55
                y += 20

    def _pack(self, items, outer_rect, align):
        packer = DrawRectPacker(items)
        results = list(packer.pack(outer_rect, align))
        for item, r in results:
            self._draw_rect(r, item)
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
        outer_rect = Rect.from_frame(50, 110, 50, 80, self.WIDTH, self.HEIGHT)

        ((locked_item, self.locked_rect), (circ_item, self.circulating_rect)) = self._pack([
            PackItem('', self.supply.thor_rune.locked_amount, ''),
            PackItem('', self.supply.thor_rune.circulating, ''),
        ], outer_rect, align=DrawRectPacker.H)

        self._pack([
            PackItem(
                self.translate.get(lock_type, lock_type),
                amount,
                self.PALETTE.get(lock_type, 'black'),
                amount if amount >= self.MIN_AMOUNT_FOR_LABEL else '')
            for lock_type, amount in self.supply.thor_rune.locked.items()
        ], self.locked_rect, align=DrawRectPacker.V)

        bonded = self.net_stats.total_bond_rune
        pooled = self.net_stats.total_rune_pooled
        free_circulating = self.supply.thor_rune.circulating - bonded - pooled

        self._pack([
            PackItem(self.loc.SUPPLY_PIC_BONDED, bonded, self.PALETTE[ThorRealms.BONDED], 'y'),
            PackItem(self.loc.SUPPLY_PIC_POOLED, pooled, self.PALETTE[ThorRealms.POOLED], 'y'),
            PackItem(self.loc.SUPPLY_PIC_CIRCULATING, free_circulating, self.PALETTE[ThorRealms.CIRCULATING], 'y'),
        ], self.circulating_rect, align=DrawRectPacker.V)

        y_up = -22
        self._add_text(self.locked_rect.shift_from_origin(0, y_up), self.loc.SUPPLY_PIC_SECTION_LOCKED, stroke_width=0)
        self._add_text(self.circulating_rect.shift_from_origin(0, y_up),
                       self.loc.SUPPLY_PIC_SECTION_CIRCULATING, stroke_width=0)

        self._add_text(self.old_rect.shift_from_origin(-34, y_up), self.loc.SUPPLY_PIC_SECTION_OLD, stroke_width=0)
