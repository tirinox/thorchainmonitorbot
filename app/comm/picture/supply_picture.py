from contextlib import suppress
from math import sqrt
from typing import List, NamedTuple

from PIL import Image

from comm.localization.eng_base import BaseLocalization
from comm.picture.common import BasePictureGenerator, DrawRectPacker, Rect, PackItem
from comm.picture.resources import Resources
from lib.constants import RUNE_IDEAL_SUPPLY, ThorRealms
from lib.draw_utils import font_estimate_size, reduce_alpha, adjust_brightness
from lib.money import short_money
from lib.plot_graph import PlotGraph
from lib.utils import async_wrap
from models.circ_supply import RuneCirculatingSupply
from models.net_stats import NetworkStats


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
            ThorRealms.LIQ_POOL: self.loc.SUPPLY_PIC_POOLED,
        }

        self.PALETTE = {
            ThorRealms.RESERVES: '#1AE6CC',
            ThorRealms.RUNEPOOL: '#28fcc4',
            ThorRealms.POL: '#0cf5b7',
            ThorRealms.BONDED: '#03CFFA',
            ThorRealms.LIQ_POOL: '#31FD9D',
            ThorRealms.CIRCULATING: '#dddddd',
            ThorRealms.CEX: '#bbb3ef',
            'Binance': '#d0a10d',
            'Kraken': '#7263d6',
            ThorRealms.TREASURY: '#35f8ec',
            ThorRealms.MAYA_POOL: '#347ce0',
            ThorRealms.BURNED: '#dd5627',
            ThorRealms.KILLED: '#9e1d0b',
        }

        self.OVERLAYS = {
            'Binance': './data/supply_chart/binance.png',
            'Kraken': './data/supply_chart/kraken.png',
            ThorRealms.BONDED: './data/supply_chart/bonded.png',
            ThorRealms.CIRCULATING: './data/supply_chart/circulating.png',
            ThorRealms.MAYA_POOL: './data/supply_chart/maya.png',
            ThorRealms.LIQ_POOL: './data/supply_chart/wave.png',
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
        legend_items = [
            ThorRealms.RESERVES,
            ThorRealms.RUNEPOOL,
            ThorRealms.POL,
            ThorRealms.BONDED,
            ThorRealms.LIQ_POOL,
            'Binance',
            'Kraken',
            ThorRealms.TREASURY,
            ThorRealms.MAYA_POOL,
            ThorRealms.BURNED,
            ThorRealms.KILLED,
        ]
        for title in legend_items:
            color = self.PALETTE.get(title, '#fff')
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

        # Top level layout (horizontal)
        rune_pool = self.net_stats.total_rune_pool
        reserves_1st_column = self.supply.in_reserves + rune_pool
        (
            locked_rect,
            working_rect,
            circulating_rect,
        ) = self._pack([
            PackItem('', reserves_1st_column, ''),
            PackItem('', self.supply.working, ''),
            PackItem('', self.supply.circulating, ''),
        ], outer_rect, align=DrawRectPacker.H)

        # Column 1: Reserves
        reserve = self.supply.find_by_realm(ThorRealms.RESERVES)[0]

        self._pack([
            PackItem(
                self.translate.get(reserve.realm, reserve.realm),
                reserve.amount,
                self.PALETTE.get(reserve.realm, 'black'),
                meta_data=meta(realm=reserve.realm)
            ),
            PackItem(self.loc.SUPPLY_PIC_RUNE_POOL, rune_pool, self.PALETTE[ThorRealms.RUNEPOOL],
                     meta(realm=ThorRealms.RUNEPOOL, label='up' if rune_pool < 1e6 else '')),
            PackItem(self.loc.SUPPLY_PIC_POL, self.net_stats.total_rune_pol, self.PALETTE[ThorRealms.POL],
                     meta(realm=ThorRealms.POL)),

        ], locked_rect, align=DrawRectPacker.V)

        # Column 2: Bond and Pool (working Rune)
        bonded = self.net_stats.total_bond_rune
        pooled = self.net_stats.total_rune_lp

        self._pack([
            PackItem(self.loc.SUPPLY_PIC_BONDED, bonded, self.PALETTE[ThorRealms.BONDED],
                     meta(realm=ThorRealms.BONDED)),
            PackItem(self.loc.SUPPLY_PIC_POOLED, pooled, self.PALETTE[ThorRealms.LIQ_POOL],
                     meta(realm=ThorRealms.LIQ_POOL)),
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
            items.append(PackItem(self.loc.SUPPLY_PIC_BURNED_LENDING, abs(self.supply.lending_burnt_rune),
                                  self.PALETTE[ThorRealms.BURNED], meta(value=True, realm=ThorRealms.BURNED)))
        if self.supply.adr12_burnt_rune > 0:
            items.append(PackItem(self.loc.SUPPLY_PIC_BURNED_ADR12, abs(self.supply.adr12_burnt_rune),
                                  self.PALETTE[ThorRealms.BURNED], meta(value=True, realm=ThorRealms.BURNED)))
        if self.supply.killed_switched > 0:
            items.append(PackItem(self.loc.SUPPLY_PIC_SECTION_KILLED,
                                  self.supply.killed_switched,
                                  self.PALETTE[ThorRealms.KILLED],
                                  meta(value=True, realm=ThorRealms.KILLED)))
        self._pack(items, killed_rect, align=DrawRectPacker.H)
