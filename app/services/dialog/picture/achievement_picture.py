from localization.achievements.ach_eng import AchievementsEnglishLocalization
from services.dialog.picture.common import BasePictureGenerator
from services.jobs.achievements import AchievementRecord
from services.lib.date_utils import today_str
from services.lib.utils import async_wrap


class AchievementPicture(BasePictureGenerator):
    BASE = './data'
    WIDTH = 512
    HEIGHT = 512

    def generate_picture_filename(self):
        return f'thorchain-ach-{self.rec.key}-{today_str()}.png'

    def __init__(self, loc: AchievementsEnglishLocalization, rec: AchievementRecord):
        # noinspection PyTypeChecker
        super().__init__(loc)
        self.loc = loc
        self.rec = rec

    @async_wrap
    def _get_picture_sync(self):
        pass

    async def prepare(self):
        return await super().prepare()
