import asyncio
import operator
from collections import defaultdict
from datetime import datetime, timedelta

from PIL import Image, ImageDraw

from localization.manager import BaseLocalization
from services.dialog.picture.common import BasePictureGenerator
from services.dialog.picture.resources import Resources
from services.lib.constants import BTC_SYMBOL, ETH_SYMBOL, BNB_BUSD_SYMBOL, ETH_USDC_SYMBOL, ETH_USDT_SYMBOL
from services.lib.draw_utils import paste_image_masked, result_color, TC_LIGHTNING_BLUE, TC_YGGDRASIL_GREEN, \
    dual_side_rect, COLOR_OF_PROFIT
from services.lib.money import pretty_money, short_dollar, short_money, format_percent, Asset
from services.lib.texts import bracketify
from services.lib.utils import async_wrap
from services.models.flipside import EventKeyStats, FSLockedValue, FSFees, FSAffiliateCollectors, FSSwapVolume, \
    FSSwapCount, FSSwapRoutes


def sum_by_attribute(daily_list, attr_name, klass=None, f_sum=sum):
    return f_sum(
        getattr(obj, attr_name)
        for objects_for_day in daily_list
        for objects in objects_for_day.values()
        for obj in objects
        if not klass or isinstance(obj, klass)
    )


def sum_by_attribute_pair(first_list, second_list, attr_name, klass=None, f_sum=sum):
    return (
        sum_by_attribute(first_list, attr_name, klass, f_sum),
        sum_by_attribute(second_list, attr_name, klass, f_sum)
    )


class KeyStatsPictureGenerator(BasePictureGenerator):
    BASE = './data'
    BG_FILE = f'{BASE}/key_weekly_stats_bg.png'

    def __init__(self, loc: BaseLocalization, event: EventKeyStats):
        super().__init__(loc)
        self.bg = Image.open(self.BG_FILE)
        self.event = event
        self.logos = {}
        self.r = Resources()
        self.btc_logo = None
        self.eth_logo = None
        self.usdt_logo = self.usdc_logo = self.busd_logo = None

    FILENAME_PREFIX = 'thorchain_weekly_stats'

    async def prepare(self):
        self.btc_logo, self.eth_logo, self.usdt_logo, self.usdc_logo, self.busd_logo = await asyncio.gather(
            self.r.logo_downloader.get_or_download_logo_cached(BTC_SYMBOL),
            self.r.logo_downloader.get_or_download_logo_cached(ETH_SYMBOL),
            self.r.logo_downloader.get_or_download_logo_cached(ETH_USDT_SYMBOL),
            self.r.logo_downloader.get_or_download_logo_cached(ETH_USDC_SYMBOL),
            self.r.logo_downloader.get_or_download_logo_cached(BNB_BUSD_SYMBOL),
        )
        logo_size = int(self.btc_logo.width * 0.66)
        self.usdc_logo.thumbnail((logo_size, logo_size))
        self.usdt_logo.thumbnail((logo_size, logo_size))
        self.busd_logo.thumbnail((logo_size, logo_size))

    @staticmethod
    def format_period_dates_string(end_date: datetime, days=7):
        start_date = end_date - timedelta(days=days)
        date_format = '%d %B %Y'
        return f'{start_date.strftime(date_format)} – {end_date.strftime(date_format)}'

    @staticmethod
    def percent_change(old_v, new_v):
        return (new_v - old_v) / old_v * 100.0 if old_v else 0.0

    def text_and_change(self, old_v, new_v, draw, x, y, text, font_main, font_second, fill='#fff',
                        x_shift=20, y_shift=6):
        draw.text((x, y), text, font=font_main, fill=fill, anchor='lm')

        percent = self.percent_change(old_v, new_v)

        size_x, _ = draw.textsize(text, font=font_main)
        if abs(percent) > 0.1:
            draw.text(
                (x + size_x + x_shift, y + y_shift),
                bracketify(short_money(percent, postfix='%', signed=True)),
                anchor='lm', fill=result_color(percent), font=font_second
            )

    @staticmethod
    def _get_top_affiliate(daily_list):
        collectors = defaultdict(float)
        for objects_for_day in daily_list:
            for objects in objects_for_day.values():
                for obj in objects:
                    if isinstance(obj, FSAffiliateCollectors):
                        if obj.label:
                            collectors[obj.label] += obj.fee_usd
        return list(sorted(collectors.items(), key=operator.itemgetter(1), reverse=True))

    @staticmethod
    def _get_to_swap_routes(daily_list):
        collectors = defaultdict(int)
        for objects_for_day in daily_list:
            for objects in objects_for_day.values():
                for obj in objects:
                    if isinstance(obj, FSSwapRoutes):
                        if obj.assets:
                            collectors[obj.assets] += obj.swap_count
        return list(sorted(collectors.items(), key=operator.itemgetter(1), reverse=True))

    @async_wrap
    def _get_picture_sync(self):
        # prepare data
        r, loc, e = self.r, self.loc, self.event
        prev_lock, curr_lock = e.series.get_prev_and_curr(e.days, FSLockedValue)
        prev_lock: FSLockedValue = prev_lock[0] if prev_lock else None
        curr_lock: FSLockedValue = curr_lock[0] if curr_lock else None

        curr_data, prev_data = e.series.get_current_and_previous_range(e.days)
        total_revenue_usd, prev_total_revenue_usd = sum_by_attribute_pair(
            curr_data, prev_data, 'total_earnings_usd', FSFees)
        block_rewards_usd, prev_block_rewards_usd = sum_by_attribute_pair(
            curr_data, prev_data, 'block_rewards_usd', FSFees)
        liq_fee_usd, prev_liq_fee_usd = sum_by_attribute_pair(curr_data, prev_data, 'liquidity_fees_usd', FSFees)
        aff_fee_usd, prev_aff_fee_usd = sum_by_attribute_pair(curr_data, prev_data, 'fee_usd', FSAffiliateCollectors)

        block_ratio = block_rewards_usd / total_revenue_usd if total_revenue_usd else 100.0
        organic_ratio = liq_fee_usd / total_revenue_usd if total_revenue_usd else 100.0

        aff_collectors = self._get_top_affiliate(curr_data)

        swap_count, prev_swap_count = sum_by_attribute_pair(curr_data, prev_data, 'swap_count', FSSwapCount)
        usd_volume, prev_usd_volume = sum_by_attribute_pair(curr_data, prev_data, 'swap_volume_usd', FSSwapVolume)

        unique_swap, prev_unique_swap = sum_by_attribute_pair(curr_data, prev_data, 'unique_swapper_count',
                                                              FSSwapCount, max)

        swap_routes = self._get_to_swap_routes(curr_data)

        # prepare painting stuff
        image = self.bg.copy()
        draw = ImageDraw.Draw(image)

        # Week dates
        draw.text((1862, 236), self.format_period_dates_string(self.event.end_date, days=self.event.days),
                  fill='#fff', font=r.fonts.get_font_bold(52),
                  anchor='rm')

        # Block subtitles
        subtitle_font = r.fonts.get_font_bold(40)
        for x, caption in [
            (378, loc.TEXT_PIC_STATS_NATIVE_ASSET_VAULTS),
            (1024, loc.TEXT_PIC_STATS_WEEKLY_REVENUE),
            (2048 - 378, loc.TEXT_PIC_STATS_SWAP_INFO)
        ]:
            draw.text((x, 362),
                      caption, fill='#c6c6c6', font=subtitle_font,
                      anchor='ms')  # s stands for "Baseline"

        # ----- Block vaults -----

        font_small_n = r.fonts.get_font(34)
        font_indicator_name = r.fonts.get_font(42)

        coin_x = 151
        values = [
            (e.get_sum((BTC_SYMBOL,), previous=True), e.get_sum((BTC_SYMBOL,))),
            (e.get_sum((ETH_SYMBOL,), previous=True), e.get_sum((ETH_SYMBOL,))),
            (e.get_stables_sum(previous=True), e.get_stables_sum()),
        ]
        vaults_y = [473, 622, 771]
        postfixes = [' ₿', ' Ξ', 'usd']
        stable_y = vaults_y[2]

        paste_image_masked(image, self.btc_logo, (coin_x, 473))
        paste_image_masked(image, self.eth_logo, (coin_x, 622))

        paste_image_masked(image, self.busd_logo, (coin_x - 30, stable_y))
        paste_image_masked(image, self.usdt_logo, (coin_x, stable_y))
        paste_image_masked(image, self.usdc_logo, (coin_x + 30, stable_y))

        coin_font = r.fonts.get_font_bold(54)

        for postfix, y, (old_v, new_v) in zip(postfixes, vaults_y, values):
            if postfix == 'usd':
                text = short_dollar(new_v)
            else:
                text = pretty_money(new_v, postfix=postfix)

            text_x = coin_x + 110

            self.text_and_change(old_v, new_v, draw, text_x, y,
                                 text, coin_font, font_small_n)

        # helper:

        def _indicator(_x, _y, name, text_value, old_value, new_value, _margin=72):
            draw.text((_x, _y),
                      name,
                      anchor='lt', fill='#fff',
                      font=font_indicator_name)

            if text_value:
                self.text_and_change(
                    old_value, new_value,
                    draw, _x, _y + _margin,
                    text_value,
                    coin_font, font_small_n
                )

        # ------- total native asset pooled -------

        margin, delta_y = 78, 160
        y = 888

        _indicator(100, y, loc.TEXT_PIC_STATS_NATIVE_ASSET_POOLED,
                   short_dollar(curr_lock.total_value_pooled_usd),
                   prev_lock.total_value_pooled_usd, curr_lock.total_value_pooled_usd)

        # ------- total network security usd -------

        _indicator(100, y + delta_y, loc.TEXT_PIC_STATS_NETWORK_SECURITY,
                   short_dollar(curr_lock.total_value_bonded_usd),
                   prev_lock.total_value_bonded_usd, curr_lock.total_value_bonded_usd)

        # 2. Block
        # -------- protocol revenue -----

        x = 769

        _indicator(x, 442,
                   loc.TEXT_PIC_STATS_PROTOCOL_REVENUE,
                   short_dollar(total_revenue_usd),
                   prev_total_revenue_usd, total_revenue_usd)

        _indicator(x, 623,
                   loc.TEXT_PIC_STATS_AFFILIATE_REVENUE,
                   short_dollar(aff_fee_usd),
                   prev_aff_fee_usd, aff_fee_usd)

        # ----- top 3 affiliates table -----

        draw.text((x, 780),
                  loc.TEXT_PIC_STATS_TOP_AFFILIATE,
                  fill='#fff',
                  font=font_indicator_name)

        n_max = 3
        y = 844
        y_margin = 60
        font_aff = r.fonts.get_font_bold(40)
        for i, (label, fee_usd) in zip(range(1, n_max + 1), aff_collectors):
            text = f'{i}. {label}'
            draw.text((x, y),
                      text,
                      font=font_aff,
                      fill='#fff')
            w, _ = draw.textsize(text, font=font_aff)

            draw.text((x + w + 20, y + 6),
                      bracketify(short_dollar(fee_usd)),
                      # fill='#afa',
                      fill=COLOR_OF_PROFIT,
                      font=font_small_n)

            y += y_margin

        # ----- organic fees vs block rewards

        draw.text((x, 1050),
                  loc.TEXT_PIC_STATS_ORGANIC_VS_BLOCK_REWARDS,
                  fill='#fff',
                  font=r.fonts.get_font(37))

        font_fee = r.fonts.get_font_bold(32)
        x_right = 1283

        y_p, y_bar = 1142, 1105

        dual_side_rect(draw, x, y_bar, x_right, y_bar + 14,
                       liq_fee_usd, block_rewards_usd,
                       TC_YGGDRASIL_GREEN, TC_LIGHTNING_BLUE)

        draw.text((x, y_p),
                  format_percent(organic_ratio, threshold=0.0),
                  font=font_fee,
                  anchor='lm',
                  fill=TC_YGGDRASIL_GREEN)

        draw.text((x_right, y_p),
                  format_percent(block_ratio, threshold=0.0),
                  font=font_fee,
                  anchor='rm',
                  fill=TC_LIGHTNING_BLUE)

        # 3. Block

        x, y = 1423, 442

        # ---- unique swappers -----

        _indicator(x, y,
                   loc.TEXT_PIC_STATS_UNIQUE_SWAPPERS,
                   pretty_money(unique_swap),
                   prev_unique_swap, unique_swap)

        # ---- count of swaps ----

        y += 159

        _indicator(x, y,
                   loc.TEXT_PIC_STATS_NUMBER_OF_SWAPS,
                   pretty_money(swap_count),
                   prev_swap_count, swap_count)

        # ---- swap volume -----

        y += 159

        _indicator(x, y,
                   loc.TEXT_PIC_STATS_USD_VOLUME,
                   short_dollar(usd_volume),
                   prev_usd_volume, usd_volume)

        # ---- routes ----

        y += 159

        draw.text((x, y),
                  loc.TEXT_PIC_STATS_TOP_SWAP_ROUTES,
                  fill='#fff',
                  font=font_indicator_name)

        y += 60
        y_margin = 60

        font_routes = r.fonts.get_font_bold(40)
        for i, (label, count) in zip(range(1, n_max + 1), swap_routes):
            left, right = str(label).split(' to ')
            l_asset, r_asset = Asset(left), Asset(right)

            text = f'{i}. {l_asset.name} → {r_asset.name}'
            draw.text((x, y),
                      text,
                      font=font_routes,
                      fill='#fff')
            w, _ = draw.textsize(text, font=font_routes)

            draw.text((x + w + 20, y + 6),
                      bracketify(pretty_money(count)),
                      fill='#ccc',
                      font=font_small_n)

            y += y_margin

        return image
