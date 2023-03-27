import asyncio
from datetime import datetime, timedelta

from PIL import Image, ImageDraw

from localization.manager import BaseLocalization
from services.dialog.picture.common import BasePictureGenerator
from services.dialog.picture.resources import Resources
from services.lib.constants import BTC_SYMBOL, ETH_SYMBOL, BNB_BUSD_SYMBOL, ETH_USDC_SYMBOL, ETH_USDT_SYMBOL
from services.lib.draw_utils import paste_image_masked
from services.lib.money import pretty_money, short_dollar
from services.lib.utils import async_wrap
from services.models.flipside import EventKeyStats


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

    @async_wrap
    def _get_picture_sync(self):
        # prepare data
        ...

        # prepare painting stuff
        r, loc, e = self.r, self.loc, self.event
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
                      caption, fill='#fff', font=subtitle_font,
                      anchor='ms')  # s stands for "Baseline"

        # ----- Block vaults -----

        coin_x = 151

        paste_image_masked(image, self.btc_logo, (coin_x, 473))
        paste_image_masked(image, self.eth_logo, (coin_x, 622))

        stable_y = 622 - 473 + 622
        paste_image_masked(image, self.busd_logo, (coin_x - 30, stable_y))
        paste_image_masked(image, self.usdt_logo, (coin_x, stable_y))
        paste_image_masked(image, self.usdc_logo, (coin_x + 30, stable_y))

        coin_font = r.fonts.get_font_bold(54)

        btc_new = e.get_sum((BTC_SYMBOL,))
        btc_old = e.get_sum((BTC_SYMBOL,), previous=True)

        draw.text(
            (coin_x + 100, 473), pretty_money(btc_new, postfix=' ₿'),
            font=coin_font,
            fill='#fff', anchor='lm'
        )

        eth_new = e.get_sum((ETH_SYMBOL,))
        eth_old = e.get_sum((ETH_SYMBOL,), previous=True)

        draw.text(
            (coin_x + 100, 622), pretty_money(eth_new, postfix=' Ξ'),
            font=coin_font,
            fill='#fff', anchor='lm'
        )

        usd_new = e.get_stables_sum()
        usd_old = e.get_stables_sum(previous=True)

        draw.text(
            (coin_x + 100, stable_y), short_dollar(usd_new),
            font=coin_font,
            fill='#fff', anchor='lm'
        )

        return image
