from localization.manager import BaseLocalization
from services.dialog.picture.common import BasePictureGenerator
from services.lib.utils import async_wrap


class SaversPictureGenerator(BasePictureGenerator):
    def __init__(self, loc: BaseLocalization):
        super().__init__(loc)

    FILENAME_PREFIX = 'thorchain_savers'

    @async_wrap
    def _get_picture_sync(self):
        # todo
        return None
