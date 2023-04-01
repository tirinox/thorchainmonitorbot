import asyncio
from datetime import datetime, timedelta

from PIL import Image, ImageDraw

from localization.manager import BaseLocalization
from services.dialog.picture.common import BasePictureGenerator
from services.dialog.picture.resources import Resources
from services.lib.constants import BTC_SYMBOL, ETH_SYMBOL, BNB_BUSD_SYMBOL, ETH_USDC_SYMBOL, ETH_USDT_SYMBOL
from services.lib.draw_utils import paste_image_masked, result_color
from services.lib.money import pretty_money, short_dollar, short_money
from services.lib.texts import bracketify
from services.lib.utils import async_wrap
from services.models.flipside import EventKeyStats, FSLockedValue, FSFees, FSAffiliateCollectors


def sum_by_attribute(daily_list, attr_name, klass=None):
    return sum(
        getattr(obj, attr_name)
        for objects_for_day in daily_list
        for objects in objects_for_day.values()
        for obj in objects
        if not klass or isinstance(obj, klass)
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
        draw.text((x + size_x + x_shift, y + y_shift),
                  bracketify(short_money(percent, postfix='%', signed=True)),
                  anchor='lm', fill=result_color(percent), font=font_second)

    @async_wrap
    def _get_picture_sync(self):
        # prepare data
        r, loc, e = self.r, self.loc, self.event
        prev_lock, curr_lock = e.series.get_prev_and_curr(e.days, FSLockedValue)
        prev_lock: FSLockedValue = prev_lock[0] if prev_lock else None
        curr_lock: FSLockedValue = curr_lock[0] if curr_lock else None

        curr_data, prev_data = e.series.get_current_and_previous_range(e.days)

        total_revenue_usd = sum_by_attribute(curr_data, 'total_earnings_usd', FSFees)
        prev_total_revenue_usd = sum_by_attribute(prev_data, 'total_earnings_usd', FSFees)

        aff_fee_usd = sum_by_attribute(curr_data, 'fee_usd', FSAffiliateCollectors)
        prev_aff_fee_usd = sum_by_attribute(prev_data, 'fee_usd', FSAffiliateCollectors)

        # prepare painting stuff
        image = self.bg.copy()
        draw = ImageDraw.Draw(image)

        # Week dates
        draw.text((1862, 236), self.format_period_dates_string(self.event.end_date, days=self.event.days),
                  fill='#fff', font=r.fonts.get_font_bold(62),
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

        # ------- total native asset pooled -------

        margin, delta_y = 78, 154
        y = 880

        draw.text((100, y),
                  loc.TEXT_PIC_STATS_NATIVE_ASSET_POOLED,
                  anchor='lt', fill='#fff',
                  font=r.fonts.get_font(42))

        self.text_and_change(prev_lock.total_value_pooled_usd, curr_lock.total_value_pooled_usd,
                             draw, 100, y + margin,
                             short_dollar(curr_lock.total_value_pooled_usd),
                             coin_font, font_small_n)

        # ------- total network security usd -------

        draw.text((100, y + delta_y),
                  loc.TEXT_PIC_STATS_NETWORK_SECURITY,
                  anchor='lt', fill='#fff',
                  font=r.fonts.get_font(42))

        self.text_and_change(prev_lock.total_value_bonded_usd, curr_lock.total_value_bonded_usd,
                             draw, 100, y + margin + delta_y,
                             short_dollar(curr_lock.total_value_bonded_usd),
                             coin_font, font_small_n)

        # 2. Block

        # -------- protocol revenue -----

        print()

        return image
