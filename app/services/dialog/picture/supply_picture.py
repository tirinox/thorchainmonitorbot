from contextlib import suppress
from math import sqrt
from typing import List, NamedTuple

from PIL import Image

from localization.eng_base import BaseLocalization
from services.dialog.picture.common import BasePictureGenerator, DrawRectPacker, Rect, PackItem
from services.dialog.picture.resources import Resources
from services.jobs.fetch.circulating import RuneCirculatingSupply, ThorRealms
from services.lib.constants import RUNE_IDEAL_SUPPLY
from services.lib.draw_utils import font_estimate_size, reduce_alpha, adjust_brightness
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

    MIN_FONT_SIZE = 30
    MAX_FONT_SIZE = 50

    MIN_VALUE_FONT_SIZE = 40
    MAX_VALUE_FONT_SIZE = 100

    def _draw_rect(self, r: Rect, item: PackItem, outline='black'):
        if item.color:
            r = r.extend(-1)
            # self.gr.draw.rectangle(r.coordinates, item.color, outline=outline)
            with suppress(ValueError):
                self.gr.draw.rounded_rectangle(r.coordinates, radius=14, fill=item.color, outline=outline)

        if path := item.meta_key('overlay_path'):
            self._put_overlay(r, path, alpha=0.2)

        if item.meta_key('show_weight') and item.weight > 1e6:
            font_sz = min(self.MAX_VALUE_FONT_SIZE, max(self.MIN_FONT_SIZE, int(sqrt(item.weight) / 80)))
            font = self.res.fonts.get_font(font_sz)
            text = short_money(item.weight)

            self._add_text(r.center, text,
                           anchor='mm',
                           font=font,
                           fill=adjust_brightness(item.color, 1.1),
                           stroke_fill=adjust_brightness(item.color, 0.5))
        if item.label:
            label_pos = item.meta_key('label_pos')
            if label_pos == 'up':
                px, py, anchor = 10, -8, 'lb'
            elif label_pos == 'left':
                px, py, anchor = -10, 0, 'rt'
            elif label_pos == 'right':
                px, py, anchor = 10 + r.w, 0, 'lt'
            else:
                px, py, anchor = 10, 14, 'lt'

            font_sz = min(self.MAX_FONT_SIZE, max(self.MIN_FONT_SIZE, int(sqrt(item.weight) / 0.7e2)))
            font = self.res.fonts.get_font(font_sz)

            self._add_text(r.shift_from_origin(px, py), item.label, anchor=anchor,
                           fill=adjust_brightness(item.color, 0.7),
                           stroke_fill=adjust_brightness(item.color, 0.3),
                           font=font)

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
        self.maya_pool = self.supply.total_rune_in_realm(ThorRealms.MAYA_POOL)

        self.res = Resources()

        self.left = 80
        self.right = 80
        self.top = 80
        self.bottom = 160

        self.font_block = self.res.fonts.get_font_bold(50)

        self.gr = PlotGraph(self.WIDTH, self.HEIGHT)

        self.translate = {
            ThorRealms.CIRCULATING: self.loc.SUPPLY_PIC_CIRCULATING,
            ThorRealms.RESERVES: self.loc.SUPPLY_PIC_RESERVES,
            ThorRealms.STANDBY_RESERVES: self.loc.SUPPLY_PIC_UNDEPLOYED,
            ThorRealms.BONDED: self.loc.SUPPLY_PIC_BONDED,
            ThorRealms.POOLED: self.loc.SUPPLY_PIC_POOLED,
        }

        self.PALETTE = {
            ThorRealms.RESERVES: '#1AE6CC',
            # ThorRealms.STANDBY_RESERVES: '#02B662',
            ThorRealms.BONDED: '#03CFFA',
            ThorRealms.POOLED: '#31FD9D',
            ThorRealms.CIRCULATING: '#dddddd',
            ThorRealms.CEX: '#bbb3ef',
            ThorRealms.TREASURY: '#35f8ec',
            ThorRealms.KILLED: '#9e1d0b',
            ThorRealms.BURNED: '#dd5627',
            ThorRealms.MAYA_POOL: '#255fb0',
            'Binance': '#d0a10d',
            'Kraken': '#7263d6',
        }

        self.OVERLAYS = {
            'Binance': './data/supply_chart/binance.png',
            'Kraken': './data/supply_chart/kraken.png',
            ThorRealms.BONDED: './data/supply_chart/bonded.png',
            ThorRealms.CIRCULATING: './data/supply_chart/circulating.png',
            ThorRealms.MAYA_POOL: './data/supply_chart/maya.png',
            ThorRealms.POOLED: './data/supply_chart/wave.png',
            ThorRealms.RESERVES: './data/supply_chart/reserve.png',
            ThorRealms.STANDBY_RESERVES: './data/supply_chart/standby.png',
            ThorRealms.TREASURY: './data/supply_chart/treasury.png',
            ThorRealms.BURNED: './data/supply_chart/burned.png',
        }

    @async_wrap
    def _get_picture_sync(self):
        self.gr.title = ''
        self.gr.top = 80
        self._plot()
        self._add_legend()

        return self.gr.finalize()

    def _add_legend(self):
        x = orig_x = self.left + 8
        y_step = 37
        y = self.HEIGHT - 110
        legend_font = self.res.fonts.get_font_bold(30)
        for title, color in self.PALETTE.items():
            title = self.translate.get(title, title)
            dx, _ = font_estimate_size(legend_font, title)
            self.gr.plot_legend_unit(x, y, color, title, font=legend_font, size=26)
            x += dx + 70
            if x >= self.WIDTH - self.right - 180:
                x = orig_x
                y += y_step

    def _pack(self, items, outer_rect, align):
        if not items:
            return []
        packer = DrawRectPacker(items)
        results = list(packer.pack(outer_rect, align))
        for item, r in results:
            self._draw_rect(r, item)
        return [r[1] for r in results]

    def _put_overlay(self, r: Rect, path, alpha=0.5):
        source = Image.open(path).convert('RGBA')
        source.thumbnail((int(r.w), int(r.h)), Image.Resampling.LANCZOS)
        source = reduce_alpha(source, alpha)
        self.gr.image.paste(source, (int(r.x), int(r.y + r.h - source.height)), source)

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
        outer_rect = Rect.from_frame(self.left, self.top, self.right, self.bottom, self.WIDTH, self.HEIGHT)

        def meta(label='', value=True, realm=''):
            return {'show_weight': value, 'label_pos': label, 'overlay_path': self.OVERLAYS.get(realm)}

        just_value = meta(value=False)

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
                meta_data=meta(realm=item.realm)
            )
            for item in self.supply.find_by_realm((ThorRealms.RESERVES,))
        ], locked_rect, align=DrawRectPacker.V)

        # Column 2: Bond and Pool (working Rune)
        bonded = self.net_stats.total_bond_rune
        pooled = self.net_stats.total_rune_pooled

        self._pack([
            PackItem(self.loc.SUPPLY_PIC_BONDED, bonded, self.PALETTE[ThorRealms.BONDED],
                     meta(realm=ThorRealms.BONDED)),
            PackItem(self.loc.SUPPLY_PIC_POOLED, pooled, self.PALETTE[ThorRealms.POOLED],
                     meta(realm=ThorRealms.POOLED))
        ], working_rect, align=DrawRectPacker.V)

        # Column 3: Circulating Rune

        # Circulating
        other_circulating = self.supply.circulating - self.supply.treasury - self.supply.in_cex
        burned_killed_rune = RUNE_IDEAL_SUPPLY - self.supply.total

        [cex_rect, other_rect, killed_rect] = self._pack([
            PackItem('', self.supply.in_cex, ''),  # CEX Block
            PackItem('', other_circulating, ''),
            PackItem('', max(1, burned_killed_rune), ''),  # Killed & burned
        ], circulating_rect, align=DrawRectPacker.V)

        cex_items = [
            PackItem(
                (it.name if it.amount > 2e6 else ''),
                it.amount,
                self.PALETTE.get(it.name, self.PALETTE.get(ThorRealms.CEX)),
                meta_data=meta(realm=it.name)
            )
            for it in sorted(
                self.supply.find_by_realm(ThorRealms.CEX, join_by_name=True),
                key=lambda it: it.amount, reverse=True
            )
        ]
        self._pack(cex_items, cex_rect, align=DrawRectPacker.H)

        # Circulating, Maya, Treasury, Burned, Killed

        self._pack([
            PackItem(self.loc.SUPPLY_PIC_CIRCULATING, other_circulating, self.PALETTE[ThorRealms.CIRCULATING],
                     meta(realm=ThorRealms.CIRCULATING)),
            PackItem(self.loc.SUPPLY_PIC_TREASURY, self.supply.treasury, self.PALETTE[ThorRealms.TREASURY],
                     meta(realm=ThorRealms.TREASURY)),
            PackItem(self.loc.SUPPLY_PIC_MAYA, self.maya_pool, self.PALETTE[ThorRealms.MAYA_POOL],
                     meta(realm=ThorRealms.MAYA_POOL, label='up')),
        ], other_rect, align=DrawRectPacker.INSIDE_LARGEST)

        items = []
        if self.supply.lending_burnt_rune > 0:
            items.append(PackItem(self.loc.SUPPLY_PIC_BURNED, abs(self.supply.lending_burnt_rune),
                                  self.PALETTE[ThorRealms.BURNED], meta(value=True, realm=ThorRealms.BURNED)))
        if self.supply.killed_switched > 0:
            items.append(PackItem(self.loc.SUPPLY_PIC_SECTION_KILLED,
                                  self.supply.killed_switched,
                                  self.PALETTE[ThorRealms.KILLED],
                                  meta(value=True, realm=ThorRealms.KILLED)))
        self._pack(items, killed_rect, align=DrawRectPacker.H)
