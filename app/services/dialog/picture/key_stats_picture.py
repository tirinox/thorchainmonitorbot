import asyncio
from datetime import datetime, timedelta

from PIL import Image, ImageDraw

from localization.manager import BaseLocalization
from services.dialog.picture.common import BasePictureGenerator
from services.dialog.picture.resources import Resources
from services.lib.constants import BTC_SYMBOL, ETH_SYMBOL
from services.lib.utils import async_wrap
from services.models.flipside import KeyStatsDelta


class KeyStatsPictureGenerator(BasePictureGenerator):
    BASE = './data'
    BG_FILE = f'{BASE}/key_weekly_stats_bg.png'

    def __init__(self, loc: BaseLocalization, data: KeyStatsDelta):
        super().__init__(loc)
        self.bg = Image.open(self.BG_FILE)
        self.event = data
        self.logos = {}
        self.r = Resources()
        self.btc_logo = None
        self.eth_logo = None

    FILENAME_PREFIX = 'thorchain_weekly_stats'

    async def prepare(self):
        self.btc_logo, self.eth_logo = await asyncio.gather(
            self.r.logo_downloader.get_or_download_logo_cached(BTC_SYMBOL),
            self.r.logo_downloader.get_or_download_logo_cached(ETH_SYMBOL)
        )

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
        r = self.r
        image = self.bg.copy()
        draw = ImageDraw.Draw(image)

        end_date = datetime.today()
        days = 7

        draw.text((1862, 236), self.format_period_dates_string(end_date, days=days),
                  fill='#fff', font=r.fonts.get_font(72),
                  anchor='rm')

        return image
