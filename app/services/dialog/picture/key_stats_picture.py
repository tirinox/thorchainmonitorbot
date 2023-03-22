from PIL import Image

from localization.manager import BaseLocalization
from services.dialog.picture.common import BasePictureGenerator
from services.dialog.picture.resources import Resources
from services.lib.utils import async_wrap
from services.models.pol import EventPOL


class KeyStatsPictureGenerator(BasePictureGenerator):
    BASE = './data'
    BG_FILE = f'{BASE}/key_stats_report_bg.png'  # todo

    def __init__(self, loc: BaseLocalization, event: EventPOL):
        super().__init__(loc)
        self.bg = Image.open(self.BG_FILE)
        self.event = event
        self.logos = {}

    FILENAME_PREFIX = 'thorchain_weekly_stats'

    async def prepare(self):
        pass
        # r = Resources()
        # logo = await r.logo_downloader.get_or_download_logo_cached(vault.asset)
        # self.logos[vault.asset] = logo

    @async_wrap
    def _get_picture_sync(self):
        # prepare data
        ...

        # prepare painting stuff
        r = Resources()
        image = self.bg.copy()
        # draw = ImageDraw.Draw(image)
        return image
