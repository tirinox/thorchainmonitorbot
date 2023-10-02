from contextlib import suppress
from typing import List, NamedTuple

from localization.eng_base import BaseLocalization
from services.dialog.picture.common import BasePictureGenerator, DrawRectPacker, Rect, PackItem
from services.dialog.picture.resources import Resources
from services.jobs.fetch.circulating import RuneCirculatingSupply, ThorRealms
from services.lib.draw_utils import font_estimate_size
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
    WIDTH = 2048
    HEIGHT = 1536
    MIN_AMOUNT_FOR_LABEL = 1.5e6

    CHART_TEXT_COLOR = 'white'

    FILENAME_PREFIX = 'thorchain_supply'

    def _draw_rect(self, r: Rect, item: PackItem, outline='black'):
        if item.color:
            r = r.extend(-1)
            # self.gr.draw.rectangle(r.coordinates, item.color, outline=outline)
            with suppress(ValueError):
                self.gr.draw.rounded_rectangle(r.coordinates, radius=14, fill=item.color, outline=outline)
        if item.label:
            self._add_text(r.shift_from_origin(10, 8), item.label)
        meta = item.meta_data
        if meta:
            font_sz = min(max(20, int(item.weight / 1e6)), 120)
            font = self.res.fonts.get_font(font_sz)
            text = short_money(item.weight)

            self._add_text(r.center, text,
                           anchor='mm',
                           font=font,
                           fill=item.color or 'white')

    def _add_text(self, xy, text, fill='white', stroke_fill='black', stroke_width=1, anchor=None, font=None):
        self.gr.draw.text(xy, text,
                          fill=fill,
                          font=font or self.font_block,
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
        self.font_block = self.res.fonts.get_font_bold(40)

        self.gr = PlotGraph(self.WIDTH, self.HEIGHT)

        self.translate = {
            ThorRealms.CIRCULATING: self.loc.SUPPLY_PIC_CIRCULATING,
            ThorRealms.RESERVES: self.loc.SUPPLY_PIC_RESERVES,
            ThorRealms.UNDEPLOYED_RESERVES: self.loc.SUPPLY_PIC_UNDEPLOYED,
            ThorRealms.BONDED: self.loc.SUPPLY_PIC_BONDED,
            ThorRealms.POOLED: self.loc.SUPPLY_PIC_POOLED,
        }

        self.PALETTE = {
            ThorRealms.RESERVES: '#2980b9',
            ThorRealms.UNDEPLOYED_RESERVES: '#517496',
            ThorRealms.BONDED: '#00ffe4',
            ThorRealms.POOLED: '#0bdf65',
            ThorRealms.CIRCULATING: '#f8e287',
            ThorRealms.CEX: '#d0f359',  # todo
            ThorRealms.TREASURY: '#f8e287',  # todo
            ThorRealms.KILLED: '#ff4444',  # todo
            ThorRealms.BURNED: '#fb1d00',  # todo
        }

    @async_wrap
    def _get_picture_sync(self):
        self.gr.title = ''
        self.gr.top = 80
        self._plot()
        self._add_legend()

        return self.gr.finalize()

    def _add_legend(self):
        x = 60
        y = self.HEIGHT - 55
        legend_font = self.res.fonts.get_font_bold(30)
        for title, color in self.PALETTE.items():
            title = self.translate.get(title, title)
            dx, _ = font_estimate_size(legend_font, title)
            self.gr.plot_legend_unit(x, y, color, title, font=legend_font, size=26)
            x += dx + 70
            if x >= self.WIDTH - 100:
                x = 55
                y += 20

    def _pack(self, items, outer_rect, align):
        packer = DrawRectPacker(items)
        results = list(packer.pack(outer_rect, align))
        for item, r in results:
            self._draw_rect(r, item)
        return [r[1] for r in results]

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
        outer_rect = Rect.from_frame(50, 100, 50, 120, self.WIDTH, self.HEIGHT)

        # Title
        # y_up = -60
        # self._add_text(locked_rect.shift_from_origin(0, y_up), self.loc.SUPPLY_PIC_SECTION_LOCKED, stroke_width=0)
        #
        # self._add_text(circulating_rect.shift_from_origin(0, y_up),
        #                self.loc.SUPPLY_PIC_SECTION_CIRCULATING, stroke_width=0)

        # Top level layout (horizontal)
        (
            locked_rect,
            working_rect,
            circulating_rect,
        ) = self._pack([
            PackItem('', self.supply.in_reserves, ''),
            PackItem('', self.supply.working, ''),
            PackItem('', self.supply.circulating, ''),
        ], outer_rect, align=DrawRectPacker.H)

        # Column 1: Reserves
        self._pack([
            PackItem(
                self.translate.get(item.realm, item.realm),
                item.amount,
                self.PALETTE.get(item.realm, 'black'),
                item.amount if item.amount >= self.MIN_AMOUNT_FOR_LABEL else ''
            )
            for item in self.supply.find_by_realm((ThorRealms.RESERVES, ThorRealms.UNDEPLOYED_RESERVES))
        ], locked_rect, align=DrawRectPacker.V)

        # Column 2: Bond and Pool (working Rune)
        bonded = self.net_stats.total_bond_rune
        pooled = self.net_stats.total_rune_pooled

        self._pack([
            PackItem(self.loc.SUPPLY_PIC_BONDED, bonded, self.PALETTE[ThorRealms.BONDED], 'y'),
            PackItem(self.loc.SUPPLY_PIC_POOLED, pooled, self.PALETTE[ThorRealms.POOLED], 'y'),
        ], working_rect, align=DrawRectPacker.V)

        # Column 3: Circulating Rune
        other_circulating = self.supply.circulating - self.supply.treasury - self.supply.in_cex
        [cex_rect, *_] = self._pack([
            PackItem('', self.supply.in_cex, ''),  # CEX Block
            PackItem(self.loc.SUPPLY_PIC_TREASURY, self.supply.treasury, self.PALETTE[ThorRealms.TREASURY], 'y'),
            PackItem(self.loc.SUPPLY_PIC_CIRCULATING, other_circulating, self.PALETTE[ThorRealms.CIRCULATING], 'y'),
            PackItem(self.loc.SUPPLY_PIC_BURNED, abs(self.supply.lending_burnt_rune),
                     self.PALETTE[ThorRealms.BURNED], 'y'),
            PackItem(self.loc.SUPPLY_PIC_SECTION_KILLED,
                     self.supply.killed_switched, self.PALETTE[ThorRealms.KILLED], 'y'),
        ], circulating_rect, align=DrawRectPacker.V)

        cex_items = [
            PackItem(
                (it.name if it.amount > 2e6 else ''),
                it.amount,
                self.PALETTE[ThorRealms.CEX], 'v'
            )
            for it in sorted(
                self.supply.find_by_realm(ThorRealms.CEX, join_by_name=True),
                key=lambda it: it.amount, reverse=True
            )
        ]
        self._pack(cex_items, cex_rect, align=DrawRectPacker.H)
