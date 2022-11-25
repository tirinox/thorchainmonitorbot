from PIL import Image

from localization.manager import BaseLocalization
from services.dialog.picture.common import BasePictureGenerator
from services.dialog.picture.resources import Resources
from services.lib.utils import async_wrap
from services.notify.types.savers_stats_notify import AllSavers


class SaversPictureGenerator(BasePictureGenerator):
    BASE = './data'
    BG_FILE = f'{BASE}/savers_report_bg.png'

    def __init__(self, loc: BaseLocalization, savers: AllSavers):
        super().__init__(loc)
        self.bg = Image.open(self.BG_FILE)
        self.savers = savers
        self.logos = {}

    FILENAME_PREFIX = 'thorchain_savers'

    async def prepare(self):
        r = Resources()

        for vault in self.savers.pools:
            logo = await r.logo_downloader.get_or_download_logo_cached(vault.asset)
            self.logos[vault.asset] = logo

    @async_wrap
    def _get_picture_sync(self):
        image = self.bg.copy()

        y, dy = 120, 60

        for vault in self.savers.pools:
            logo = self.logos.get(vault.asset)
            if logo:
                logo = logo.copy()
                logo.thumbnail((40, 40))
                image.paste(logo, (50, y), logo)
            y += dy

        # todo
        return image
