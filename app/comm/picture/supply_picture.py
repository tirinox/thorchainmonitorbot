from contextlib import suppress
from math import sqrt
from typing import List, NamedTuple

from PIL import Image

from comm.localization.eng_base import BaseLocalization
from comm.picture.common import BasePictureGenerator, DrawRectPacker, Rect, PackItem
from comm.picture.resources import Resources
from lib.constants import ThorRealms
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

    MIN_FONT_SIZE = 24
    MAX_FONT_SIZE = 50

    MIN_VALUE_FONT_SIZE = 45
    MAX_VALUE_FONT_SIZE = 99

    MIN_WEIGHT_TO_DISPLAY = 1.5e6

    def _draw_rect(self, r: Rect, item: PackItem, outline='black'):
        if item.color:
            r = r.extend(-1)
            # self.gr.draw.rectangle(r.coordinates, item.color, outline=outline)
            with suppress(ValueError):
                ((x1, y1), (x2, y2)) = r.coordinates
                if y2 < y1 + 2:
                    y2 = y1 + 2
                self.gr.draw.rounded_rectangle(((x1, y1), (x2, y2)), radius=14, fill=item.color, outline=outline)

        if path := item.meta_key('overlay_path'):
            self._put_overlay(r, path, alpha=0.2)

        if item.meta_key('show_weight') and item.weight >= self.MIN_WEIGHT_TO_DISPLAY:
            font_sz = min(item.meta_key('max_value_font', self.MAX_VALUE_FONT_SIZE),
                          max(self.MIN_FONT_SIZE, int(sqrt(item.weight) / 80)))
            font = self.res.fonts.get_font(font_sz)
            text = short_money(item.weight)

            too_thin = font_sz >= r.h
            anchor = 'mm' if not too_thin else 'mb'
            value_pos = r.center if not too_thin else r.anchored_position('top', 0, -5)
            self._add_text(value_pos,
                           text,
                           anchor=anchor,
                           font=font,
                           fill=adjust_brightness(item.color, 5.1),
                           stroke_fill=adjust_brightness(item.color, 0.2))

            # if prev_value := item.meta_key('prev'):
            #     diff = item.weight - prev_value
            #     value_pos = (value_pos[0], value_pos[1] + 0.5 * font_sz + 5)
            #     if diff and abs(diff) > item.weight * 0.01:
            #         diff_text = short_money(diff, signed=True)
            #         self._add_text(value_pos, diff_text, anchor=anchor,
            #                        fill=adjust_brightness(item.color, 0.7),
            #                        stroke_fill=adjust_brightness(item.color, 0.3),
            #                        font=self.res.fonts.get_font(30))

        if item.label:
            label_pos = item.meta_key('label_pos')
            if label_pos == 'up':
                px, py, anchor = 10, -8, 'lb'
            elif label_pos == 'left':
                px, py, anchor = -10, 0, 'rt'
            elif label_pos == 'right':
                px, py, anchor = 10 + r.w, 0, 'lt'
            elif label_pos == 'tight_top':
                px, py, anchor = 10, 6, 'lt'
            else:
                px, py, anchor = 10, 14, 'lt'

            if item.weight < 0:
                self.logger.warning(f'Negative weight for {item.label}: {item.weight}')
                item = item._replace(weight=0)

            font_sz = min(
                item.meta_key('max_title_font', self.MAX_FONT_SIZE),
                max(self.MIN_FONT_SIZE, int(sqrt(item.weight) / 0.7e2))
            )
            font = self.res.fonts.get_font(font_sz)

            fill = item.meta_key('title_fill', adjust_brightness(item.color, 0.7))
            stroke = item.meta_key('title_stoke', adjust_brightness(item.color, 0.7))
            self._add_text(r.shift_from_origin(px, py), item.label, anchor=anchor,
                           fill=fill,
                           stroke_fill=stroke,
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
                 net_stats: NetworkStats,
                 prev_supply: RuneCirculatingSupply):
        super().__init__(loc)

        if not supply.bonded:
            raise ValueError('Bonded supply is not set. Please, check the data.')

        if not supply.pooled:
            raise ValueError('Pooled supply is not set. Please, check the data.')

        self.supply = supply
        self.prev_supply = prev_supply or RuneCirculatingSupply.zero()
        self.net_stats = net_stats

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
            'Bybit': '#a0a0a0',
            ThorRealms.TREASURY: '#35f8ec',
            ThorRealms.MAYA_POOL: '#347ce0',
            ThorRealms.BURNED: '#dd5627',
            ThorRealms.KILLED: '#9e1d0b',
            ThorRealms.INCOME_BURN: '#e38239',
        }

        self.OVERLAYS = {
            'Binance': './data/supply_chart/binance.png',
            'Kraken': './data/supply_chart/kraken.png',
            'Bybit': './data/supply_chart/bybit.png',
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
            ThorRealms.BONDED,
            ThorRealms.LIQ_POOL,
            ThorRealms.RUNEPOOL,
            ThorRealms.POL,
            'Binance',
            'Kraken',
            'Bybit',
            ThorRealms.TREASURY,
            ThorRealms.MAYA_POOL,
            ThorRealms.BURNED,
            ThorRealms.KILLED,
            ThorRealms.INCOME_BURN,
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

        def meta(label='', value=True, realm='', **kwargs):
            return {'show_weight': value, 'label_pos': label, 'overlay_path': self.OVERLAYS.get(realm),
                    **kwargs}

        # Top level sections
        protocol_section = self.supply.reserves_without_pol + self.supply.pol
        working_section = self.supply.runepool + self.supply.bonded + self.supply.pooled
        free_float_section = self.supply.total - protocol_section - working_section
        burned_section = self.supply.total_burned_rune

        # Top level layout (horizontal)
        (
            locked_rect,
            working_rect,
            circulating_rect,
            burned_rect,
        ) = self._pack([
            PackItem('', protocol_section, ''),
            PackItem('', working_section, ''),
            PackItem('', free_float_section, ''),
            PackItem('', burned_section, '')
        ], outer_rect, align=DrawRectPacker.H)

        # --------------------------------------------------------------------------------------------------------------
        # Column 1 is protocol section: Reserves and POL
        self._pack([
            PackItem(
                self.translate.get(ThorRealms.RESERVES, ThorRealms.RESERVES),
                self.supply.reserves_without_pol,
                self.PALETTE.get(ThorRealms.RESERVES, 'black'),
                meta_data=meta(realm=ThorRealms.RESERVES, max_value_font=80)
            ),
            PackItem(
                self.loc.SUPPLY_PIC_POL, self.supply.pol, self.PALETTE[ThorRealms.POL],
                meta(realm=ThorRealms.POL, prev=self.prev_supply.pol)
            ),
        ], locked_rect, align=DrawRectPacker.V)

        # --------------------------------------------------------------------------------------------------------------
        # Column 2: Users' Rune those are working in the protocol
        self._pack([
            PackItem(self.loc.SUPPLY_PIC_BONDED, self.supply.bonded, self.PALETTE[ThorRealms.BONDED],
                     meta(realm=ThorRealms.BONDED, prev=self.prev_supply.bonded)),
            PackItem(self.loc.SUPPLY_PIC_POOLED, self.supply.pooled, self.PALETTE[ThorRealms.LIQ_POOL],
                     meta(realm=ThorRealms.LIQ_POOL, prev=self.prev_supply.pooled)),
            PackItem(self.loc.SUPPLY_PIC_RUNE_POOL, self.supply.runepool, self.PALETTE[ThorRealms.RUNEPOOL],
                     meta(realm=ThorRealms.RUNEPOOL,
                          label='tight_top', max_title_font=24, prev=self.prev_supply.runepool
                          )),

        ], working_rect, align=DrawRectPacker.V)

        # --------------------------------------------------------------------------------------------------------------
        # Column 3: Circulating Rune

        # first, we will show CEX block
        cex_items = [
            PackItem(
                (it.name if it.amount > 2e6 else ''),
                it.amount,
                self.PALETTE.get(it.name, self.PALETTE.get(ThorRealms.CEX)),
                meta_data=meta(
                    realm=it.name, label='tight_top' if it.amount < 15e6 else None,
                    # todo: prev
                    # prev=self.prev_supply.find_by_realm(it.name).amount
                )
            )
            for it in sorted(
                self.supply.find_by_realm(ThorRealms.CEX, join_by_name=True),
                key=lambda it: it.amount, reverse=True
            )
        ]

        total_displayed_cex_rune = sum(it.weight for it in cex_items)

        other_circulating = (
                free_float_section -
                self.supply.treasury -
                total_displayed_cex_rune -
                self.supply.maya_pool
        )

        self._pack([
            *cex_items,
            PackItem(self.loc.SUPPLY_PIC_TREASURY, self.supply.treasury, self.PALETTE[ThorRealms.TREASURY],
                     meta(realm=ThorRealms.TREASURY,
                          max_title_font=24, label='tight_top',
                          prev=self.prev_supply.treasury)),
            PackItem(self.loc.SUPPLY_PIC_CIRCULATING, other_circulating, self.PALETTE[ThorRealms.CIRCULATING],
                     meta(realm=ThorRealms.CIRCULATING)),
            PackItem(
                self.loc.SUPPLY_PIC_MAYA,
                self.supply.maya_pool,
                self.PALETTE[ThorRealms.MAYA_POOL],
                meta(realm=ThorRealms.MAYA_POOL, max_title_font=30, label='up', prev=self.prev_supply.maya_pool)
            ),  # , label='up'
        ], circulating_rect, align=DrawRectPacker.V)

        # --------------------------------------------------------------------------------------------------------------
        # Column 4: Burned and Killed Rune
        adr12_burned = self.supply.adr12_burnt_rune
        killed_switched = self.supply.killed_switched

        if burned_section >= (adr12_burned + killed_switched):
            burn_items = []
            if self.supply.lending_burnt_rune > 0:
                burn_items.append(PackItem(
                    self.loc.SUPPLY_PIC_BURNED_LENDING, self.supply.lending_burnt_rune,
                    self.PALETTE[ThorRealms.BURNED],
                    meta(value=True, realm=ThorRealms.BURNED, prev=self.prev_supply.lending_burnt_rune)
                ))
            if self.supply.adr12_burnt_rune > 0:
                burn_items.append(PackItem(
                    self.loc.SUPPLY_PIC_BURNED_ADR12, adr12_burned,
                    self.PALETTE[ThorRealms.BURNED], meta(value=True, realm=ThorRealms.BURNED)
                ))
            if self.supply.killed_switched > 0:
                burn_items.append(PackItem(
                    self.loc.SUPPLY_PIC_SECTION_KILLED,
                    self.supply.killed_switched,
                    self.PALETTE[ThorRealms.KILLED],
                    meta(value=True, realm=ThorRealms.KILLED)
                ))
        else:
            # If there is no enough space for all burned sections, we will show them without distribution
            prev_burned = self.prev_supply.total_burned_rune
            burn_items = [
                PackItem(
                    self.loc.SUPPLY_PIC_BURNED_GENERAL,
                    burned_section,
                    self.PALETTE[ThorRealms.BURNED], meta(value=True, realm=ThorRealms.BURNED, prev=prev_burned)
                )
            ]

        burn_items.append(PackItem(
            self.loc.SUPPLY_PIC_BURNED_INCOME,
            self.supply.burnt_rune_from_income,
            self.PALETTE[ThorRealms.INCOME_BURN],
            meta(
                realm=ThorRealms.INCOME_BURN,
                value=True,
                prev=self.prev_supply.burnt_rune_from_income,
                label='up', title_fill='#ffcf40'
            )
        ))

        self._pack(burn_items, burned_rect, align=DrawRectPacker.V)
